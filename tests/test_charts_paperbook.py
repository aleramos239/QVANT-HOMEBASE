"""The PAPER account (homebase/charts/paperbook.py): the backtester's fill law on a fixture tick stream, parity
with run_session on the same prints, the desk's caps, restart persistence, the no-broker import rule, and the
chart service's /api/paper/* routes (a paper order never produces a desk call). No network, no broker, no
~/futures_ticks: every book lives in tmp_path."""
from __future__ import annotations

import ast
import asyncio
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import et_ns
from homebase.charts import paperbook as pb
from homebase.charts import server
from homebase.charts.desk import DeskLink
from homebase.charts.paperbook import PAPER_ID, PaperBook
from homebase.charts.server import create_app
from tests.charts_util import D as CD, rows, session_ms
from tests.test_backtest_engine import D, Script, tape
from tests.test_charts_desk_server import BASE_URL, WS_HOST, QuietFeed, key_file, live_app
from tests.test_charts_server import archive, next_of, next_within

T0 = et_ns(D, "09:30:00")                     # 2024-03-05 09:30 ET: every fixture places its orders here


def book(tmp_path=None, root="NQ", clock_ns=T0, **kw) -> PaperBook:
    return PaperBook(None if tmp_path is None else tmp_path / "paper" / "book.jsonl", roots=[root],
                     clock_ms=lambda: clock_ns // 1_000_000, **kw)


def feed(b: PaperBook, prints, root="NQ", d=D):
    """prints: [("HH:MM:SS[.mmm]", price), ...] on day d, fed one by one."""
    for t, p in prints:
        hms, _, ms = t.partition(".")
        b.on_print(root, et_ns(d, hms) + int(ms or 0) * 1_000_000, p)


_cid = iter(range(10 ** 6))


def order(b, side, typ, qty=1, price=None, sl=None, tp=None, trigger=None, tif=None, root="NQ"):
    body = {"client_id": f"c{next(_cid)}", "accounts": [PAPER_ID], "root": root, "side": side, "qty": qty, "type": typ}
    if price is not None:
        body["price"] = price
    for k, v in (("sl_price", sl), ("tp_price", tp), ("trigger_price", trigger), ("tif", tif)):
        if v is not None:
            body[k] = v
    return b.act("order", body)["results"][PAPER_ID]


def act(b, action, **body):
    return b.act(action, {"client_id": f"c{next(_cid)}", **body})["results"][PAPER_ID]


def fills(b):
    return [(f["side"], f["qty"], f["price"]) for f in b.fills]


def net(b, root="NQ"):
    return (b.pos.get(root) or {}).get("net", 0)


# ---- the fill law, rule by rule (engine.py) -----------------------------------------------------------------
def test_a_stop_fills_on_touch_and_pays_one_tick_of_slip():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    assert order(b, "Buy", "Stop", price=101.0)["ok"]
    feed(b, [("09:30:01", 100.75)])
    assert fills(b) == []
    feed(b, [("09:30:02", 101.0)])                        # touch, not through
    assert fills(b) == [("Buy", 1, 101.25)]


def test_a_stop_gapped_through_pays_the_gap_plus_slip():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Sell", "Stop", price=99.0)
    feed(b, [("09:30:01", 97.5)])
    assert fills(b) == [("Sell", 1, 97.25)]               # min(99, 97.5) - 1 tick


def test_a_limit_needs_one_tick_of_penetration_and_fills_at_its_price():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Limit", price=99.0)
    feed(b, [("09:30:01", 99.0), ("09:30:02", 99.0)])      # touched twice, never through
    assert fills(b) == []
    feed(b, [("09:30:03", 98.75)])
    assert fills(b) == [("Buy", 1, 99.0)]                 # AT the limit, no slip


def test_a_market_order_fills_at_the_next_print_not_one_it_already_saw():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market")
    assert fills(b) == []
    feed(b, [("09:30:01", 100.5)])
    assert fills(b) == [("Buy", 1, 100.75)]               # the next print + 1 tick


def test_commission_is_four_dollars_a_round_turn_per_contract():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market", qty=2)
    feed(b, [("09:30:01", 100.0)])                       # in at 100.25
    order(b, "Sell", "Market", qty=2)
    feed(b, [("09:30:02", 101.0)])                       # out at 100.75
    assert net(b) == 0
    assert b.realized == pytest.approx(0.5 * 20 * 2 - 8.0)
    v = b.view()
    assert v["balance"] == pb.START_BALANCE + 12.0 and v["realized_pnl"] == 12.0 and v["positions"] == []


def test_the_tick_grid_comparison_is_epsilon_tolerant():
    b = book(root="CL")
    feed(b, [("09:29:59", 64.0)], root="CL")
    order(b, "Buy", "Stop", price=64.02, root="CL")
    feed(b, [("09:30:01", 64.01 + 0.01)], root="CL")      # 64.02000000000001 is a touch, not "above"
    assert fills(b) == [("Buy", 1, 64.03)]
    b2 = book(root="CL")
    feed(b2, [("09:29:59", 64.0)], root="CL")
    order(b2, "Sell", "Limit", price=64.01, root="CL")
    feed(b2, [("09:30:01", 64.01 + 0.01)], root="CL")     # 64.02 == 64.01 + 1 tick: penetration
    assert fills(b2) == [("Sell", 1, 64.01)]


def test_a_brackets_legs_go_live_on_the_print_after_the_entry_and_one_cancels_the_other():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    assert order(b, "Buy", "Stop", price=101.0, sl=99.0, tp=103.0)["ok"]
    # the legs wait on their entry: shown "Suspended" (the broker's OSO legs look the same; fix round 1, item 2)
    assert [(o["type"], o["role"], o["status"]) for o in b.view()["orders"]] == \
        [("Stop", "entry", "Working"), ("Stop", "sl", "Suspended"), ("Limit", "tp", "Suspended")]
    feed(b, [("09:30:01", 104.0)])                                      # entry through the TP level: TP not live yet
    assert fills(b) == [("Buy", 1, 104.25)] and net(b) == 1
    assert sorted((o["type"], o["role"], o["status"]) for o in b.view()["orders"]) == \
        [("Limit", "tp", "Working"), ("Stop", "sl", "Working")]
    feed(b, [("09:30:02", 103.25)])                                     # 1-tick through the TP
    assert fills(b)[-1] == ("Sell", 1, 103.0) and net(b) == 0
    assert b.view()["orders"] == []                                    # the SL went with it


def test_orders_triggered_by_one_print_fill_oldest_first():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    a = order(b, "Buy", "Stop", price=100.5)["order_id"]
    c = order(b, "Buy", "Limit", price=101.25)["order_id"]   # marketable limit (the page refuses; the law still orders)
    feed(b, [("09:30:01", 100.75)])
    assert [f["order_id"] for f in b.fills] == [a, c]


def test_a_triggered_stop_limit_fills_at_the_market_capped_by_its_limit_not_at_the_limit():
    """Fix round 1, I1 -- the reviewer's NQ numbers: trigger 20000.25, limit 20025.00 (100 ticks away)."""
    b = book()
    feed(b, [("09:29:59", 20000.0)])
    order(b, "Buy", "StopLimit", price=20025.0, trigger=20000.25)
    feed(b, [("09:30:01", 20000.25)])                    # triggered, never filled on its trigger print
    assert fills(b) == []
    feed(b, [("09:30:02", 20000.5)])
    assert fills(b) == [("Buy", 1, 20000.75)]            # the print + 1 tick, not 20025.00
    s2 = book()
    feed(s2, [("09:29:59", 20000.0)])
    order(s2, "Sell", "StopLimit", price=19999.0, trigger=19999.75)
    feed(s2, [("09:30:01", 19999.75), ("09:30:02", 19999.25)])
    assert fills(s2) == [("Sell", 1, 19999.0)]           # print - 1 tick would be worse than the cap: the cap


def test_a_stop_limit_gapped_past_its_limit_rests_then_needs_penetration():
    b = book()
    feed(b, [("09:29:59", 20000.0)])
    order(b, "Buy", "StopLimit", price=20001.0, trigger=20000.25)
    feed(b, [("09:30:01", 20000.25), ("09:30:02", 20002.0)])     # triggered, then beyond the limit: rests
    assert fills(b) == [] and b.orders[next(iter(b.orders))].kind == "limit"
    feed(b, [("09:30:03", 20001.0)])                               # touch only
    assert fills(b) == []
    feed(b, [("09:30:04", 20000.75)])
    assert fills(b) == [("Buy", 1, 20001.0)]                       # at the limit, 1-tick penetration


# ---- parity with the backtester on the same prints ----------------------------------------------------------
PARITY = [
    # (name, prints after the anchor, the entry: (side, engine kind, price, sl, tp))
    ("stop gap -> tp", [("09:30:01", 112.0), ("09:31", 127.5)], ("long", "stop", 110.0, 105.0, 127.25)),
    ("stop touch -> sl gap", [("09:30:01", 110.0), ("09:31", 104.0)], ("long", "stop", 110.0, 105.25, 125.0)),
    ("short stop -> tp", [("09:30:01", 89.0), ("09:30:30", 89.0), ("09:31", 79.75)], ("short", "stop", 90.0, 95.0, 80.0)),
    ("limit touch no fill, then fill -> sl", [("09:30:01", 95.0), ("09:30:02", 94.75), ("09:31", 90.0)],
     ("long", "limit", 95.0, 90.0, 100.0)),
    ("same-print tp then sl", [("09:30:01", 110.0), ("09:31", 125.5), ("09:31", 105.0)], ("long", "stop", 110.0, 105.25, 125.25)),
    ("same-print sl then tp", [("09:30:01", 110.0), ("09:31", 105.0), ("09:31", 125.5)], ("long", "stop", 110.0, 105.25, 125.25)),
    ("market -> tp", [("09:30:01", 100.5), ("09:30:05", 103.0)], ("long", "market", None, 99.0, 102.75)),
]


@pytest.mark.parametrize("name,after,entry", PARITY, ids=[p[0] for p in PARITY])
def test_parity_with_run_session_on_the_same_prints(name, after, entry):
    side, kind, price, sl, tp = entry
    prints = [("09:29:59", 100.0)] + after

    def fire(ctx, s):
        if kind == "market":
            ctx.market(side, sl=sl, tp=tp)
        else:
            getattr(ctx, f"{kind}_entry")(side, price, sl=sl, tp=tp)

    strat = Script({"09:30:00": fire}, move=False)
    strat.placement_ms = 0
    trades = run_session(strat, tape(prints), Costs(), qty=1).trades
    assert len(trades) == 1 and trades[0].exit_reason in ("tp", "sl"), name
    t = trades[0]

    b = book()
    feed(b, prints[:1])
    typ = {"stop": "Stop", "limit": "Limit", "market": "Market"}[kind]
    assert order(b, "Buy" if side == "long" else "Sell", typ, price=price, sl=sl, tp=tp)["ok"]
    feed(b, prints[1:])
    assert len(b.fills) == 2 and net(b) == 0
    ent, ex = b.fills
    assert ent["price"] == t.entry_price and ex["price"] == t.exit_price
    assert ex["role"] == t.exit_reason
    assert round(b.realized, 2) == t.net
    assert ent["time"] == pb._iso(t.entry_ns) and ex["time"] == pb._iso(t.exit_ns)


# ---- the desk's caps and price checks ----------------------------------------------------------------------
def test_ten_per_order():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    r = order(b, "Buy", "Market", qty=11)
    assert r["ok"] is False and r["refused"] and "1-10" in r["error"]
    assert order(b, "Buy", "Market", qty=10)["ok"]


def test_twenty_per_position_counting_working_orders_on_that_side():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market", qty=10)
    feed(b, [("09:30:01", 100.0)])
    order(b, "Buy", "Limit", qty=8, price=95.0)          # worst case 18
    r = order(b, "Buy", "Limit", qty=3, price=94.0)      # 21
    assert r["ok"] is False and "20" in r["error"]
    assert order(b, "Buy", "Limit", qty=2, price=94.0)["ok"]     # exactly 20
    assert order(b, "Sell", "Limit", qty=10, price=110.0)["ok"]  # a sell shrinks |net|: allowed


def test_a_stop_on_the_wrong_side_or_with_no_price_yet_is_refused():
    b = book()
    r = order(b, "Buy", "Stop", price=101.0)
    assert r["ok"] is False and "no NQ print" in r["error"]
    feed(b, [("09:29:59", 100.0)])
    assert "above the last" in order(b, "Buy", "Stop", price=100.0)["error"]
    assert "below the last" in order(b, "Sell", "Stop", price=100.0)["error"]
    assert "losing side" in order(b, "Buy", "Limit", price=99.0, sl=99.5)["error"]
    assert "winning side" in order(b, "Sell", "Limit", price=101.0, tp=101.5)["error"]


def test_a_malformed_body_or_a_foreign_account_is_a_400_never_a_guess():
    b = book()
    with pytest.raises(ValueError):
        b.act("order", {"client_id": "x", "accounts": [PAPER_ID, "sim047"], "root": "NQ", "side": "Buy",
                        "qty": 1, "type": "Market"})
    with pytest.raises(ValueError):
        b.act("cancel", {"client_id": "x", "account": "sim047", "order_id": "1"})
    with pytest.raises(ValueError):
        b.act("order", {"client_id": "x", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1,
                        "type": "Market", "price": 100.0})
    with pytest.raises(ValueError):
        b.act("bot-kill", {"client_id": "x", "strategy": "nq930"})
    with pytest.raises(ValueError):                               # fix round 1, M7: every key must name PAPER
        b.act("order", {"client_id": "x", "accounts": [PAPER_ID], "account": "sim047", "root": "NQ", "side": "Buy",
                        "qty": 1, "type": "Market"})
    with pytest.raises(ValueError):
        b.act("flatten", {"client_id": "x", "root": "NQ"})


def test_a_repeated_client_id_is_answered_once():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    body = {"client_id": "same", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Limit",
            "price": 99.0}
    assert b.act("order", body) == b.act("order", body)
    assert len(b.view()["orders"]) == 1


# ---- modify / cancel / flatten / reverse ---------------------------------------------------------------------
def test_modify_cancel_and_cancel_symbol():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    lim = order(b, "Buy", "Limit", price=99.0)["order_id"]
    stp = order(b, "Buy", "Stop", price=102.0)["order_id"]
    assert act(b, "modify", account=PAPER_ID, order_id=lim, price=98.0)["ok"]
    assert [o["price"] for o in b.view()["orders"] if o["order_id"] == lim] == [98.0]
    assert "above the last" in act(b, "modify", account=PAPER_ID, order_id=stp, price=99.0)["error"]
    assert act(b, "cancel", account=PAPER_ID, order_id=lim)["ok"]
    assert "not working" in act(b, "cancel", account=PAPER_ID, order_id=lim)["error"]
    assert act(b, "cancel-symbol", accounts=[PAPER_ID], root="NQ")["ok"]
    assert b.view()["orders"] == []


def test_flatten_cancels_the_brackets_and_closes_at_the_next_print():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market", qty=3, sl=95.0, tp=110.0)
    feed(b, [("09:30:01", 100.0)])
    assert net(b) == 3 and len(b.view()["orders"]) == 2
    assert act(b, "flatten", accounts=[PAPER_ID], root="NQ")["ok"]
    assert [o["type"] for o in b.view()["orders"]] == ["Market"]
    feed(b, [("09:30:02", 101.0)])
    assert net(b) == 0 and b.view()["orders"] == [] and fills(b)[-1] == ("Sell", 3, 100.75)


def test_reverse_closes_then_opens_the_other_way():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    assert "no NQ position" in act(b, "reverse", accounts=[PAPER_ID], root="NQ")["error"]
    order(b, "Buy", "Market", qty=2)
    feed(b, [("09:30:01", 100.0)])
    assert act(b, "reverse", accounts=[PAPER_ID], root="NQ")["ok"]
    feed(b, [("09:30:02", 100.0)])
    assert net(b) == -2 and b.pos["NQ"]["avg"] == 99.75


def test_a_flattens_closing_order_never_expires():
    """Fix round 1, M4: a flatten sent with no print left in the session still closes at the next session's first."""
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market", qty=2, sl=90.0)
    feed(b, [("09:30:01", 100.0)])
    act(b, "flatten", accounts=[PAPER_ID], root="NQ")
    feed(b, [("19:00:00", 98.0)])                                  # the next session: it fills, it does not expire
    assert net(b) == 0 and fills(b)[-1] == ("Sell", 2, 97.75)


def test_a_day_entry_expires_with_its_session_but_a_positions_legs_do_not():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Limit", price=90.0)                           # Day
    gtc = order(b, "Buy", "Limit", price=89.0, tif="GTC")["order_id"]
    order(b, "Buy", "Market", sl=80.0)
    feed(b, [("09:30:01", 100.0)])
    feed(b, [("19:00:00", 100.0)])                                 # the next session (18:00 ET roll)
    left = {(o["order_id"], o["role"]) for o in b.view()["orders"]}
    assert (gtc, "entry") in left and any(r == "sl" for _, r in left) and len(left) == 2


# ---- restart persistence -------------------------------------------------------------------------------------
def test_the_book_survives_a_restart(tmp_path):
    b = book(tmp_path)
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Stop", price=101.0, sl=99.0, tp=103.0, qty=2)
    order(b, "Sell", "Limit", price=110.0)
    feed(b, [("09:30:01", 101.0)])                                 # entry in: legs live
    order(b, "Buy", "Market")
    feed(b, [("09:30:02", 102.0)])
    before = b.view()
    assert before["positions"][0]["net"] == 3 and len(before["orders"]) == 3
    assert (tmp_path / "paper" / "book.jsonl").exists()

    b2 = book(tmp_path)
    assert b2.view() == before
    feed(b2, [("09:30:03", 103.25)])                               # the TP still works after the restart
    assert fills(b2)[-1] == ("Sell", 2, 103.0) and net(b2) == 1
    assert order(b2, "Buy", "Market")["order_id"] not in {o["order_id"] for o in before["orders"]}


def test_a_torn_last_line_never_swallows_the_next_event_across_two_restarts(tmp_path):
    """Fix round 1, I2 -- the reviewer's scenario: a torn fill line, a restart, a re-fill appended, a 2nd restart."""
    b = book(tmp_path)
    feed(b, [("09:29:59", 100.0)])
    oid = order(b, "Buy", "Market")["order_id"]
    feed(b, [("09:30:01", 100.0)])
    p = tmp_path / "paper" / "book.jsonl"
    raw = p.read_bytes()
    p.write_bytes(raw[:-15])                                   # the crash tore the fill line: no newline
    b2 = book(tmp_path)
    assert net(b2) == 0 and oid in b2.orders                   # the fill never landed: the order is still working
    assert p.read_bytes().endswith(b"\n")                      # and the torn tail is gone before any append
    feed(b2, [("09:30:02", 101.0)])                            # it fills (once) on the next print
    assert net(b2) == 1
    b3 = book(tmp_path)
    assert net(b3) == 1 and oid not in b3.orders and b3.view() == b2.view()
    feed(b3, [("09:30:03", 102.0)])
    assert net(b3) == 1                                        # never a third fill


def test_a_failed_append_changes_nothing(tmp_path, monkeypatch):
    """Fix round 1, M5: persisted first -- a disk error leaves the book as it was, and a retry is not a duplicate."""
    b = book(tmp_path)
    feed(b, [("09:29:59", 100.0)])
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(pb._jsonl, "append", boom)
    body = {"client_id": "x1", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Limit", "price": 99.0}
    with pytest.raises(OSError):
        b.act("order", body)
    assert b.orders == {}
    monkeypatch.undo()
    assert b.act("order", body)["results"][PAPER_ID]["ok"] and len(b.orders) == 1


def test_a_torn_line_does_not_lose_the_rest_of_the_book(tmp_path):
    b = book(tmp_path)
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Limit", price=95.0)
    p = tmp_path / "paper" / "book.jsonl"
    p.write_text(p.read_text() + '{"ev": "fill", "id": "99"\n')
    assert len(book(tmp_path).view()["orders"]) == 1


# ---- it never reaches a broker ---------------------------------------------------------------------------------
FORBIDDEN = ("homebase.broker", "homebase.trading", "homebase.desk_api", "homebase.charts.desk", "homebase.engine",
             "homebase.timer", "homebase.secrets_store", "homebase.ticks", "homebase.marketdata", "httpx", "websockets")


def test_paperbook_imports_nothing_that_can_reach_a_broker():
    src = Path(pb.__file__).read_text()
    pkg = {0: "", 1: "homebase.charts", 2: "homebase"}
    direct = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            base = ".".join(x for x in (pkg[node.level], node.module or "") if x)
            direct += [f"{base}.{a.name}" if node.module is None else base for a in node.names]
        elif isinstance(node, ast.Import):
            direct += [a.name for a in node.names]
    assert [m for m in direct if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)] == [], direct
    code = ("import sys, homebase.charts.paperbook; "
            "print('\\n'.join(sorted(m for m in sys.modules if m.startswith(('homebase', 'httpx', 'websockets')))))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         cwd=Path(__file__).resolve().parent.parent).stdout.split()
    bad = [m for m in out if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)]
    assert bad == [], bad


def _desk_spy(tmp_path):
    """A desk link whose every request is recorded (the stream idles; nothing is ever answered but 200)."""
    seen = []

    async def idle():
        yield b'event: state\ndata: {"enabled": true, "accounts": [], "bot": {}}\n\n'
        await asyncio.Event().wait()

    def handler(req):
        seen.append((req.method, req.url.path))
        if req.url.path.endswith("/stream"):
            return httpx.Response(200, content=idle(), headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"results": {}})

    kp = key_file(tmp_path)
    return seen, (lambda fan: DeskLink(fan, key_path=kp, transport=httpx.MockTransport(handler)))


def test_a_paper_order_through_the_service_never_makes_a_desk_call_and_fills_on_the_live_prints(tmp_path):
    seen, factory = _desk_spy(tmp_path)
    app = live_app(tmp_path, desk_factory=factory)
    with TestClient(app, base_url=BASE_URL) as c, c.websocket_connect("/ws", headers=WS_HOST) as ws:
        first = next_of(ws, "paperbook", limit=400)
        assert first["accounts"][0]["id"] == PAPER_ID and first["accounts"][0]["env"] == "paper"
        assert first["limits"] == {"max_order_qty": 10, "max_position_qty": 20}
        body = {"client_id": "p1", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        r = c.post("/api/paper/order", json=body)
        assert r.status_code == 200 and r.json()["results"][PAPER_ID]["ok"] is True
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(CD, 9, 41), [101.0])))   # the next print fills it
        for _ in range(10):
            m = next_of(ws, "paperbook", limit=50)
            if m["accounts"][0]["positions"]:
                break
        assert m["accounts"][0]["positions"][0]["net"] == 1 and m["accounts"][0]["fills"][0]["price"] == 101.25
        assert c.get("/api/paper/book").json()["accounts"][0]["positions"][0]["avg_price"] == 101.25
    assert [p for m_, p in seen if not p.endswith("/stream")] == []          # not one desk call
    assert (tmp_path / "state" / "paper" / "book.jsonl").exists()


def test_the_desk_proxy_refuses_a_body_naming_paper(tmp_path):
    seen, factory = _desk_spy(tmp_path)
    with TestClient(live_app(tmp_path, desk_factory=factory), base_url=BASE_URL) as c:
        body = {"client_id": "d1", "accounts": ["sim047", PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        assert c.post("/api/desk/order", json=body).status_code == 400
        assert c.post("/api/desk/cancel", json={"client_id": "d2", "account": PAPER_ID, "order_id": "1"}).status_code == 400
    assert [p for _, p in seen if not p.endswith("/stream")] == []


def test_paper_routes_guard_like_the_desk_proxy(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c:
        ok = {"client_id": "g1", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        assert c.post("/api/paper/order", json=ok, headers={"origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/paper/order", content=json.dumps(ok), headers={"content-type": "text/plain"}).status_code == 415
        assert c.post("/api/paper/order", content='{"qty": NaN}', headers={"content-type": "application/json"}).status_code == 400
        assert c.post("/api/paper/bot-kill", json={"client_id": "k", "strategy": "nq930"}).status_code == 404
        bad = {**ok, "accounts": ["sim047"]}
        assert c.post("/api/paper/order", json=bad).status_code == 400
        assert c.get("/api/paper/strategies").status_code == 200             # the forward-test routes are untouched


def test_replay_has_no_paper_book(tmp_path):
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=CD, speed=50, state=tmp_path / "state")
    with TestClient(app, base_url=BASE_URL) as c:
        ok = {"client_id": "r1", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        assert c.post("/api/paper/order", json=ok).status_code == 503
        assert c.get("/api/paper/book").status_code == 503
    assert not (tmp_path / "state" / "paper" / "book.jsonl").exists()


def test_the_session_roll_is_found_without_clock_maths_on_every_print():
    for root, hhmm, want in (("NQ", "16:59:59", "2024-03-05"), ("NQ", "17:00:00", "2024-03-06"),
                             ("BTC", "17:30:00", "2024-03-05"), ("BTC", "18:00:00", "2024-03-06")):
        ms = et_ns(D, hhmm) // 1_000_000
        assert pb.session_of(ms, root) == want
        until = pb._session_until(ms, root)
        assert until > ms and pb.session_of(until - 1, root) == want != pb.session_of(until, root)
    fri = et_ns(dt.date(2024, 3, 8), "17:00:00") // 1_000_000       # a Friday close files into Monday
    assert pb.session_of(fri, "NQ") == "2024-03-11"


# ---- several paper accounts (2026-09-27 Task 2b) ---------------------------------------------------------------
def books(tmp_path, clock_ns=T0):
    return pb.PaperBooks(tmp_path / "paper", roots=["NQ"], clock_ms=lambda: clock_ns // 1_000_000)


def feed_all(bs, prints, root="NQ"):
    for t, p in prints:
        hms, _, ms = t.partition(".")
        bs.on_ticks(root, [{"ts_ns": et_ns(D, hms) + int(ms or 0) * 1_000_000, "ts_ms": 0, "price": p}])


def bs_order(bs, accounts, side="Buy", typ="Market", qty=1, **kw):
    body = {"client_id": f"c{next(_cid)}", "accounts": accounts, "root": "NQ", "side": side, "qty": qty, "type": typ, **kw}
    return bs.act("order", body)["results"]


def test_the_first_paper_accounts_book_carries_over_untouched(tmp_path):
    old = book(tmp_path)                                   # the single-account book as it was before Task 2b
    feed(old, [("09:29:59", 100.0)])
    order(old, "Buy", "Market", qty=2)
    feed(old, [("09:30:01", 100.0)])
    order(old, "Sell", "Limit", price=110.0)
    before = old.view()
    raw = (tmp_path / "paper" / "book.jsonl").read_bytes()
    bs = books(tmp_path)
    assert list(bs.books) == [PAPER_ID]
    assert bs.books[PAPER_ID].view() == {**before, "start_balance": pb.START_BALANCE}
    assert (tmp_path / "paper" / "book.jsonl").read_bytes() == raw          # not rewritten, not moved
    assert json.loads((tmp_path / "paper" / "accounts.json").read_text())["accounts"][0]["id"] == PAPER_ID


def test_several_books_are_kept_apart_and_each_survives_a_restart(tmp_path):
    bs = books(tmp_path)
    a = bs.create({"name": "Scalps", "start_balance": 25_000})["account"]
    b2 = bs.create({"name": "Swing"})["account"]
    assert (a["id"], a["label"], a["balance"], a["env"]) == ("paper-2", "Scalps", 25_000.0, "paper")
    assert (b2["id"], b2["balance"]) == ("paper-3", pb.START_BALANCE)
    feed_all(bs, [("09:29:59", 100.0)])
    r = bs_order(bs, ["paper", "paper-2"], qty=2)          # one send, two paper accounts: each its own result
    assert r["paper"]["ok"] and r["paper-2"]["ok"]
    bs_order(bs, ["paper-3"], side="Sell", qty=1)
    feed_all(bs, [("09:30:01", 101.0)])
    nets = {k: (b.pos.get("NQ") or {}).get("net", 0) for k, b in bs.books.items()}
    assert nets == {"paper": 2, "paper-2": 2, "paper-3": -1}
    assert (tmp_path / "paper" / "books" / "paper-2.jsonl").exists()
    views = bs.views()
    bs2 = books(tmp_path)
    assert bs2.views() == views
    assert [m["accounts"] for m in [bs2.message()]][0][1]["label"] == "Scalps"


def test_an_order_for_one_paper_account_never_touches_another(tmp_path):
    bs = books(tmp_path)
    bs.create({"name": "Two"})
    feed_all(bs, [("09:29:59", 100.0)])
    oid = bs_order(bs, ["paper-2"], typ="Limit", price=95.0)["paper-2"]["order_id"]
    assert bs.books[PAPER_ID].orders == {}
    body = {"client_id": "x", "account": PAPER_ID, "order_id": oid}
    assert bs.act("cancel", body)["results"][PAPER_ID]["ok"] is False      # that id is not working on PAPER
    assert len(bs.books["paper-2"].orders) == 1
    with pytest.raises(ValueError):                                          # a per-book body naming another id
        bs.books["paper-2"].act("cancel", body)
    with pytest.raises(ValueError):
        bs.act("order", {"client_id": "y", "accounts": ["paper", "sim047"], "root": "NQ", "side": "Buy", "qty": 1,
                         "type": "Market"})
    assert bs.act("flatten", {"client_id": "z", "accounts": ["paper-9"], "root": "NQ"})["results"]["paper-9"]["ok"] is False


def test_ids_never_collide_with_algo_keys_and_are_never_reused(tmp_path):
    bs = books(tmp_path)
    ids = [bs.create({"name": f"A{i}"})["account"]["id"] for i in range(3)]
    assert ids == ["paper-2", "paper-3", "paper-4"]
    assert all(":" not in i and pb.is_paper_id(i) for i in ids)
    assert not pb.is_paper_id("paper:gc_nfpcpi") and not pb.is_paper_id("paper-0") and not pb.is_paper_id("PAPER")
    assert bs.remove({"account": "paper-4"})["ok"]
    assert bs.create({"name": "A9"})["account"]["id"] == "paper-5"
    assert books(tmp_path).create({"name": "B"})["account"]["id"] == "paper-6"     # across a restart too
    with pytest.raises(ValueError):
        bs.create({"name": "a0"})                          # names are unique, case-insensitively
    with pytest.raises(ValueError):
        bs.create({"name": "paper"})                       # "PAPER" is the built-in's
    for bad in ({"name": ""}, {"name": "x" * 33}, {"name": "a\nb"}, {"name": "ok", "start_balance": 10},
                {"name": "ok", "start_balance": True}, {"name": 5}):
        with pytest.raises(ValueError):
            bs.create(bad)


def test_removal_is_refused_while_holding_anything_and_archives_the_history(tmp_path):
    bs = books(tmp_path)
    bs.create({"name": "Temp"})
    feed_all(bs, [("09:29:59", 100.0)])
    bs_order(bs, ["paper-2"], typ="Limit", price=95.0)
    r = bs.remove({"account": "paper-2"})
    assert r["ok"] is False and "flatten it first" in r["error"]
    bs.act("cancel-symbol", {"client_id": "c", "accounts": ["paper-2"], "root": "NQ"})
    bs_order(bs, ["paper-2"])
    feed_all(bs, [("09:30:01", 100.0)])
    assert "flatten it first" in bs.remove({"account": "paper-2"})["error"]      # an open position
    bs.act("flatten", {"client_id": "f", "accounts": ["paper-2"], "root": "NQ"})
    feed_all(bs, [("09:30:02", 100.0)])
    r = bs.remove({"account": "paper-2"})
    assert r["ok"] and r["archived"].startswith("paper-2-")
    assert "paper-2" not in bs.books and not (tmp_path / "paper" / "books" / "paper-2.jsonl").exists()
    arch = tmp_path / "paper" / "archive"
    assert (arch / r["archived"]).read_text().count("\n") >= 5                  # the whole log, kept
    rec = json.loads((arch / "accounts.jsonl").read_text().splitlines()[-1])
    assert rec["id"] == "paper-2" and rec["label"] == "Temp" and "removed_ms" in rec
    assert "paper-2" not in books(tmp_path).books
    assert bs.remove({"account": PAPER_ID})["ok"] is False                        # the built-in stays


def test_account_routes_create_list_remove_and_the_desk_origin(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c:
        desk = {"origin": "http://localhost:8850"}
        r = c.post("/api/paper/accounts/create", json={"name": "Desk made", "start_balance": 30000}, headers=desk)
        assert r.status_code == 200 and r.json()["account"]["id"] == "paper-2"
        assert r.headers["access-control-allow-origin"] == "http://localhost:8850"
        r = c.get("/api/paper/accounts", headers={"origin": "http://127.0.0.1:8850"})
        assert [a["id"] for a in r.json()["accounts"]] == ["paper", "paper-2"]
        assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:8850"
        pre = c.options("/api/paper/accounts/create", headers={**desk, "access-control-request-method": "POST"})
        assert pre.status_code == 204 and pre.headers["access-control-allow-origin"] == "http://localhost:8850"
        # the chart page's own origin works, without CORS headers
        own = c.post("/api/paper/accounts/create", json={"name": "Chart made"}, headers={"origin": "http://127.0.0.1:8852"})
        assert own.status_code == 200 and "access-control-allow-origin" not in own.headers
        # every other origin is refused -- another localhost port included (netguard alone ignores ports)
        for o in ("http://localhost:3000", "http://evil.example", "http://127.0.0.1:8851", "null"):
            assert c.post("/api/paper/accounts/create", json={"name": "x"}, headers={"origin": o}).status_code == 403, o
            assert c.post("/api/paper/accounts/remove", json={"account": "paper-2"}, headers={"origin": o}).status_code == 403
            assert c.get("/api/paper/accounts", headers={"origin": o}).status_code == 403
            p = c.options("/api/paper/accounts/create", headers={"origin": o, "access-control-request-method": "POST"})
            assert p.status_code == 403 and "access-control-allow-origin" not in p.headers
        # CORS for the desk origin on the account routes ONLY: an order's answer is never readable cross-origin
        order_body = {"client_id": "o", "accounts": ["paper-9"], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        assert "access-control-allow-origin" not in c.post("/api/paper/order", json=order_body, headers=desk).headers
        assert c.post("/api/paper/accounts/create", content='{"name": "x"}', headers={**desk, "content-type": "text/plain"}).status_code == 415
        assert c.post("/api/paper/accounts/create", json={"name": "Desk made"}, headers=desk).status_code == 400
        r = c.post("/api/paper/accounts/remove", json={"account": "paper-2"}, headers=desk)
        assert r.status_code == 200 and r.json()["ok"] is True
        assert c.post("/api/paper/accounts/remove", json={"account": "paper"}).json()["ok"] is False
    assert (tmp_path / "state" / "paper" / "archive" / "accounts.jsonl").exists()


def test_the_page_gets_every_paper_account_on_connect(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c, c.websocket_connect("/ws", headers=WS_HOST) as ws:
        c.post("/api/paper/accounts/create", json={"name": "Second"})
        for _ in range(10):
            m = next_of(ws, "paperbook", limit=50)
            if len(m["accounts"]) == 2:
                break
        assert [(a["id"], a["label"]) for a in m["accounts"]] == [("paper", "PAPER"), ("paper-2", "Second")]


def test_the_desk_proxy_refuses_every_paper_id(tmp_path):
    seen, factory = _desk_spy(tmp_path)
    with TestClient(live_app(tmp_path, desk_factory=factory), base_url=BASE_URL) as c:
        body = {"client_id": "d1", "accounts": ["sim047", "paper-3"], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        assert c.post("/api/desk/order", json=body).status_code == 400
        assert c.post("/api/desk/modify", json={"client_id": "d", "account": "paper-12", "order_id": "1", "price": 1}).status_code == 400
    assert [p for _, p in seen if not p.endswith("/stream")] == []


# ---- Task 2b fix round 1 -------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["​", "​PAPER", "‮evil", "a⁦b", "﻿x", "a\x85b", "a b",
                                 "a b", "a\x00b", "a‍b", "ab", "   ", "", "x" * 33, 7, None])
def test_names_refuse_invisible_control_and_bidi_characters(tmp_path, bad):
    with pytest.raises(ValueError):
        books(tmp_path).create({"name": bad})


def test_names_are_nfkc_normalised_trimmed_and_unique_by_their_normal_form(tmp_path):
    bs = books(tmp_path)
    a = bs.create({"name": "  Ｓｃａｌｐｓ  "})["account"]        # fullwidth -> NFKC "Scalps"
    assert a["label"] == "Scalps"
    for dup in ("scalps", "SCALPS", "Ｓｃａｌｐｓ", " scalps "):
        with pytest.raises(ValueError, match="already called"):
            bs.create({"name": dup})
    assert bs.create({"name": "Café 2"})["account"]["label"] == "Café 2"      # accents are fine


@pytest.mark.parametrize("fake", ["paper", "PAPER", "Paper", "ＰＡＰＥＲ", "P.A.P.E.R", "p a p e r", "P-A-P-E-R",
                                  "РАРЕR", "pаper", "PAPΕR"])
def test_the_built_in_name_is_reserved_in_any_look_alike(tmp_path, fake):
    with pytest.raises(ValueError, match="built-in"):
        books(tmp_path).create({"name": fake})


def test_a_lost_registry_never_reuses_an_id_or_adopts_an_old_log(tmp_path):
    bs = books(tmp_path)
    bs.create({"name": "one"})
    bs.create({"name": "two"})
    bs.remove({"account": "paper-3"})                       # paper-3 now only in the archive
    (tmp_path / "paper" / "accounts.json").unlink()          # the registry is gone (a lost write)
    bs2 = books(tmp_path)
    assert list(bs2.books) == [PAPER_ID]
    assert bs2.create({"name": "fresh"})["account"]["id"] == "paper-4"   # past books/paper-2 and the archived paper-3


def test_create_refuses_to_adopt_a_log_already_on_disk(tmp_path):
    bs = books(tmp_path)
    bs.next = 2
    (tmp_path / "paper" / "books").mkdir(parents=True, exist_ok=True)
    stray = tmp_path / "paper" / "books" / "paper-7.jsonl"
    stray.write_text("")
    bs._max_seen = lambda rows: 1                            # a disk scan that missed it: create itself still refuses
    bs.next = 7
    with pytest.raises(ValueError, match="already exists"):
        bs.create({"name": "x"})


@pytest.mark.parametrize("content", ["", "{", "[]", '{"next": 3}', '{"accounts": "x"}'])
def test_an_unreadable_registry_fails_closed_and_loud(tmp_path, content):
    bs = books(tmp_path)
    bs.create({"name": "kept"})
    reg = tmp_path / "paper" / "accounts.json"
    reg.write_text(content)
    logs = []
    bs2 = pb.PaperBooks(tmp_path / "paper", roots=["NQ"], clock_ms=lambda: T0 // 1_000_000, log=logs.append)
    assert bs2.broken and any("REGISTRY BROKEN" in m for m in logs)
    assert bs2.status()["broken"] == bs2.broken
    assert list(bs2.books) == [PAPER_ID]                      # the built-in still trades
    with pytest.raises(ValueError, match="unreadable"):
        bs2.create({"name": "new"})
    assert bs2.remove({"account": "paper-2"})["ok"] is False
    assert reg.read_text() == content                        # never rewritten over


def test_a_bad_registry_field_never_stops_the_service(tmp_path):
    bs = books(tmp_path)
    bs.create({"name": "one"})
    reg = tmp_path / "paper" / "accounts.json"
    d = json.loads(reg.read_text())
    d["next"] = "x"
    d["accounts"][1]["start_balance"] = "abc"
    d["accounts"].append({"id": "../../etc", "label": "bad"})
    reg.write_text(json.dumps(d))
    bs2 = books(tmp_path)
    assert bs2.broken is None and list(bs2.books) == [PAPER_ID, "paper-2"]
    assert bs2.books["paper-2"].start_balance == pb.START_BALANCE
    assert bs2.create({"name": "two"})["account"]["id"] == "paper-3"


def test_the_registry_is_written_with_fsync(tmp_path, monkeypatch):
    synced = []
    real = pb.os.fsync
    monkeypatch.setattr(pb.os, "fsync", lambda fd: (synced.append(fd), real(fd)))
    books(tmp_path).create({"name": "x"})
    assert len(synced) >= 2                                  # the file and its directory


def test_a_failed_registry_save_on_remove_writes_no_archive_record(tmp_path, monkeypatch):
    bs = books(tmp_path)
    bs.create({"name": "one"})
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(pb, "_atomic_json", boom)
    with pytest.raises(OSError):
        bs.remove({"account": "paper-2"})
    assert "paper-2" in bs.books
    assert not (tmp_path / "paper" / "archive" / "accounts.jsonl").exists()


def test_a_huge_integer_is_a_400_not_a_500(tmp_path):
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c:
        big = "1" + "0" * 400
        r = c.post("/api/paper/accounts/create", content='{"name": "x", "start_balance": ' + big + "}",
                   headers={"content-type": "application/json"})
        assert r.status_code == 400
        r = c.post("/api/paper/order", content='{"client_id": "c", "accounts": ["paper"], "root": "NQ", "side": "Buy", '
                   '"qty": 1, "type": "Limit", "price": ' + big + "}", headers={"content-type": "application/json"})
        assert r.status_code == 400


def test_a_refusal_after_the_origin_check_is_readable_by_the_desk_page(tmp_path):
    desk = {"origin": "http://localhost:8850"}
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c:
        r = c.post("/api/paper/accounts/create", content="{bad", headers={**desk, "content-type": "application/json"})
        assert r.status_code == 400 and r.headers["access-control-allow-origin"] == "http://localhost:8850"
        r = c.post("/api/paper/accounts/create", content='{"name": "x"}', headers={**desk, "content-type": "text/plain"})
        assert r.status_code == 415 and r.headers["access-control-allow-origin"] == "http://localhost:8850"
        r = c.post("/api/paper/accounts/create", json={"name": "x"}, headers={"origin": "http://localhost:3000"})
        assert r.status_code == 403 and "access-control-allow-origin" not in r.headers
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=CD, speed=50, state=tmp_path / "rstate")
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.get("/api/paper/accounts", headers=desk)
        assert r.status_code == 503 and r.headers["access-control-allow-origin"] == "http://localhost:8850"
        assert "live only" in r.json()["detail"]


# ---- exits: an SL / TP added to an open position (the chart's drag handles) ---------------------------------
def long3(b):
    feed(b, [("09:29:59", 100.0)])
    assert order(b, "Buy", "Market", qty=3)["ok"]
    feed(b, [("09:30:01", 100.0)])
    assert net(b) == 3


def exits(b, expect=None, **kw):
    """`expect`: the position the confirm showed (default: the book's own, or 1 when flat)."""
    return act(b, "exits", accounts=[PAPER_ID], root="NQ", expected_net={PAPER_ID: expect or net(b) or 1}, **kw)


def test_paper_exits_both_at_once_are_one_oco_pair_for_the_whole_position():
    b = book()
    long3(b)
    r = exits(b, sl_price=98.1, tp_price=103.0)
    assert r["ok"] is True
    rows = b.view()["orders"]
    assert [(o["type"], o["role"], o["side"], o["qty"], o["tif"]) for o in rows] == \
        [("Stop", "sl", "Sell", 3, "GTC"), ("Limit", "tp", "Sell", 3, "GTC")]
    assert rows[0]["stop_price"] == 98.0 and rows[1]["price"] == 103.0
    groups = {o.oco for o in b.orders.values()}
    assert len(groups) == 1 and None not in groups
    feed(b, [("09:30:02", 103.25)])                                   # 1-tick through the TP
    assert fills(b)[-1] == ("Sell", 3, 103.0) and net(b) == 0
    assert b.view()["orders"] == []                                   # the SL went with it


def test_paper_exits_the_stop_side_of_the_pair_fills_and_cancels_the_target():
    b = book()
    long3(b)
    exits(b, sl_price=98.0, tp_price=103.0)
    feed(b, [("09:30:02", 97.5)])                                     # gapped through the stop
    assert fills(b)[-1] == ("Sell", 3, 97.25) and net(b) == 0 and b.orders == {}


def test_paper_exits_one_print_that_could_trigger_both_fills_the_stop():
    """Same-print ambiguity is pessimistic: the Stop is placed before the Limit, and the oldest triggered order
    fills first. (A valid pair can't both trigger on one print; the law is pinned by forcing the levels.)"""
    b = book()
    long3(b)
    exits(b, sl_price=98.0, tp_price=103.0)
    for o in b.orders.values():                                       # force an overlap: stop 99, target 98.5
        o.price = 99.0 if o.type == "Stop" else 98.5
    feed(b, [("09:30:02", 99.0)])
    assert b.fills[-1]["role"] == "sl" and net(b) == 0 and b.orders == {}


def test_paper_exits_adding_the_missing_half_keeps_the_existing_price_as_one_pair():
    b = book()
    long3(b)
    assert exits(b, tp_price=103.0)["ok"]
    [tp] = b.orders.values()
    assert tp.oco is None
    assert exits(b, sl_price=98.0)["ok"]
    assert tp.id not in b.orders                                       # replaced, not left next to the pair
    kept = sorted((o.type, o.price) for o in b.orders.values())
    assert kept == [("Limit", 103.0), ("Stop", 98.0)]
    assert len({o.oco for o in b.orders.values()}) == 1
    assert list(b.orders.values())[0].type == "Stop"                  # the stop is the older of the two


def test_paper_exits_on_a_short_and_on_an_entrys_bracket_leg():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Sell", "Market", qty=2, sl=102.0)
    feed(b, [("09:30:01", 100.0)])
    assert net(b) == -2
    assert exits(b, tp_price=97.0)["ok"]
    assert sorted((o.type, o.side, o.qty, o.price) for o in b.orders.values()) == \
        [("Limit", 1, 2, 97.0), ("Stop", 1, 2, 102.0)]


@pytest.mark.parametrize("setup,body,msg", [
    ("flat", {"sl_price": 98.0}, "no NQ position on PAPER to protect"),
    ("long", {"sl_price": 100.0}, "the stop loss must be below the last price"),
    ("long", {"tp_price": 100.0}, "the target must be above the last price"),
    ("sl", {"sl_price": 97.0}, "already has a stop loss"),
    ("partial", {"tp_price": 103.0}, "exits don't match the position"),
    ("two", {"tp_price": 103.0}, "exits don't match the position"),
])
def test_paper_exits_refusals(setup, body, msg):
    b = book()
    if setup == "flat":
        feed(b, [("09:29:59", 100.0)])
    else:
        long3(b)
    if setup == "sl":
        exits(b, sl_price=98.0)
    if setup == "partial":
        order(b, "Sell", "Stop", qty=1, price=98.0)
    if setup == "two":
        order(b, "Sell", "Stop", qty=3, price=98.0)
        order(b, "Sell", "Stop", qty=3, price=97.0)
    before = dict(b.orders)
    r = exits(b, **body)
    assert r["ok"] is False and r["refused"] and msg in r["error"]
    assert b.orders == before


def test_paper_exits_need_a_price_and_split_across_paper_accounts(tmp_path):
    b = book()
    with pytest.raises(ValueError, match="an sl_price or a tp_price is required"):
        exits(b)
    bs = books(tmp_path)
    bs.create({"name": "Two"})
    feed_all(bs, [("09:29:59", 100.0)])
    bs_order(bs, [PAPER_ID, "paper-2"], qty=2)
    feed_all(bs, [("09:30:01", 100.0)])
    res = bs.act("exits", {"client_id": "e1", "accounts": [PAPER_ID, "paper-2"], "root": "NQ", "sl_price": 98.0,
                           "expected_net": {PAPER_ID: 2, "paper-2": 2}})
    assert res["results"][PAPER_ID]["ok"] and res["results"]["paper-2"]["ok"]
    assert all(len(bk.orders) == 1 for bk in bs.books.values())


def test_paper_exits_survive_a_restart(tmp_path):
    b = book(tmp_path)
    long3(b)
    exits(b, sl_price=98.0, tp_price=103.0)
    again = book(tmp_path)
    assert sorted((o.type, o.price, o.oco is not None) for o in again.orders.values()) == \
        [("Limit", 103.0, True), ("Stop", 98.0, True)]


# ---- exits, review fix round 1 -------------------------------------------------------------------------
def test_paper_exits_refuse_while_a_pending_entrys_bracket_is_held():
    """Item 2: long 1 + a working Buy Limit @ 99 with its bracket SL held: dragging a TP never touches that leg."""
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market")
    feed(b, [("09:30:01", 100.0)])
    assert order(b, "Buy", "Limit", price=99.0, sl=97.0)["ok"]
    rows = b.view()["orders"]
    assert [(o["type"], o["side"], o["status"]) for o in rows] == [("Limit", "Buy", "Working"), ("Stop", "Sell", "Suspended")]
    before = dict(b.orders)
    r = exits(b, tp_price=103.0)
    assert r["refused"] and r["error"] == "a pending order's bracket is waiting in NQ on PAPER — cancel it or let it fill first"
    assert b.orders == before
    leg = rows[1]["order_id"]                                   # the held leg can be moved and cancelled, like a broker's
    assert act(b, "modify", account=PAPER_ID, order_id=leg, price=96.0)["ok"]
    assert b.orders[leg].price == 96.0 and b.orders[leg].status == "held"
    assert act(b, "cancel", account=PAPER_ID, order_id=leg)["ok"] and leg not in b.orders
    assert exits(b, tp_price=103.0)["ok"] is True               # nothing held any more


def test_paper_exits_refuse_a_position_other_than_the_one_confirmed():
    """Item 5."""
    b = book()
    long3(b)
    r = exits(b, expect=2, sl_price=98.0)
    assert r["refused"] and r["error"] == "the NQ position on PAPER changed since you confirmed (+2 → +3) — nothing done"
    assert "(-3 → +3)" in exits(b, expect=-3, sl_price=98.0)["error"]
    for bad in (None, {}, {PAPER_ID: 0}, {PAPER_ID: True}, {PAPER_ID: 2.0}, {"paper-2": 3}):
        body = {"accounts": [PAPER_ID], "root": "NQ", "sl_price": 98.0}
        if bad is not None:
            body["expected_net"] = bad
        with pytest.raises(ValueError, match="expected_net"):
            act(b, "exits", **body)
    assert b.orders == {}


def test_paper_exits_need_a_streamed_root_and_a_fresh_print():
    """Item 7: the desk's QUOTE_MAX_AGE_S (30 s) and QUOTE_MAX_FUTURE_S (5 s), against the book's clock."""
    clock = {"ms": T0 // 1_000_000}
    b = PaperBook(None, roots=["NQ"], clock_ms=lambda: clock["ms"])
    long3(b)                                                    # last print 09:30:01, the clock at 09:30:00
    clock["ms"] += 32_000                                       # 31 s after the last print (09:30:01)
    r = exits(b, sl_price=98.0)
    assert r["refused"] and r["error"] == "no NQ print in the last 30 s — an exit needs a fresh price"
    clock["ms"] -= 2_000                                        # 29 s
    assert exits(b, sl_price=98.0)["ok"] is True
    ahead = PaperBook(None, roots=["NQ"], clock_ms=lambda: T0 // 1_000_000 - 6_000)   # the print 7 s ahead of us
    long3(ahead)
    assert "fresh price" in exits(ahead, sl_price=98.0)["error"]
    other = PaperBook(None, roots=["ES"], clock_ms=lambda: T0 // 1_000_000)
    feed(other, [("09:29:59", 100.0)], root="NQ")
    r = act(other, "exits", accounts=[PAPER_ID], root="NQ", sl_price=98.0, expected_net={PAPER_ID: 1})
    assert r["refused"] and r["error"] == "NQ is not streamed by this chart service — no prints to fill against"


def test_a_held_bracket_leg_moves_only_on_its_side_of_its_entry():
    """Review round 2, C: a pending entry's legs are checked against the ENTRY's price, not the last print."""
    b = book()
    feed(b, [("09:29:59", 100.0)])
    assert order(b, "Buy", "Limit", price=95.0, sl=93.0, tp=98.0)["ok"]     # entry 95 below the market
    rows = {o["role"]: o["order_id"] for o in b.view()["orders"]}
    mv = lambda oid, px: act(b, "modify", account=PAPER_ID, order_id=oid, price=px)
    r = mv(rows["sl"], 96.0)                                               # above the entry: not a stop loss any more
    assert r["refused"] and r["error"] == "the stop loss must be on the losing side of its entry (95.0)"
    assert mv(rows["sl"], 94.0)["ok"] and b.orders[rows["sl"]].price == 94.0   # below the entry, though far below last
    assert mv(rows["tp"], 94.75)["error"] == "the target must be on the winning side of its entry (95.0)"
    assert mv(rows["tp"], 99.0)["ok"]                                         # 99 < last 100: fine for a pending leg
    b.orders[rows["tp"]].parent = "999"                                    # the entry can't be identified: refused
    assert "can't find the entry" in mv(rows["tp"], 99.5)["error"]
    s = book()                                                              # a short entry's legs mirror it
    feed(s, [("09:29:59", 100.0)])
    order(s, "Sell", "StopLimit", price=98.5, trigger=99.0, sl=101.0, tp=96.0)
    legs = {o["role"]: o["order_id"] for o in s.view()["orders"]}
    assert "losing side of its entry (99.0)" in act(s, "modify", account=PAPER_ID, order_id=legs["sl"], price=98.75)["error"]
    assert "winning side of its entry (98.5)" in act(s, "modify", account=PAPER_ID, order_id=legs["tp"], price=98.75)["error"]
    assert act(s, "modify", account=PAPER_ID, order_id=legs["tp"], price=97.0)["ok"]



# ---- fast-paper (2026-09-27): a Market fills at once -- the live book, else the quote, else the next print ------
NOW_MS = T0 // 1_000_000                       # the fixture book's clock


def q_(bid=99.75, ask=100.0, age_ms=500, now_ms=NOW_MS, **kw):
    """A trade-row quote as Quotes.quote_of gives it: age_ms before the book's clock, 5 lots shown each side, its row's
    trade at the ask (neutral for both sides)."""
    return {"bid": bid, "ask": ask, "trade": ask, "bid_size": 5, "ask_size": 5, "ts_ms": now_ms - age_ms, **kw}


def l2(bids=((99.75, 2), (99.5, 1), (99.25, 3)), offers=((100.0, 1), (100.25, 1), (100.5, 5)), age_ms=300,
       now_ms=NOW_MS):
    """A Level 2 book as Depth.book_of gives it: best first, age_ms before the book's clock."""
    return {"bids": [list(x) for x in bids], "offers": [list(x) for x in offers], "ts_ms": now_ms - age_ms}


def live(quote=None, depth=None, root="NQ", tmp_path=None, clock_ns=T0, printed_ms=1000, px=100.0):
    """A book whose quote_of / book_of answer src["quote"] / src["book"] for `root` -- the tests change src in place --
    on a market that is matching: `root` printed `px` printed_ms before the clock (None: no print yet)."""
    src = {"quote": quote, "book": depth}
    b = book(tmp_path, root=root, clock_ns=clock_ns, quote_of=lambda r: src["quote"] if r == root else None,
             book_of=lambda r: src["book"] if r == root else None)
    if printed_ms is not None:
        b.on_print(root, clock_ns - printed_ms * 1_000_000, px)
    return b, src


def et(d, hms):
    return et_ns(dt.date.fromisoformat(d), hms)


@pytest.mark.parametrize("when, open_", [
    ("2024-03-05 16:59:59", True), ("2024-03-05 17:00:00", False), ("2024-03-05 17:59:59", False),   # a Tuesday break
    ("2024-03-05 18:00:00", True),
    ("2024-03-08 16:59:59", True), ("2024-03-08 17:00:00", False), ("2024-03-08 20:00:00", False),   # Friday close
    ("2024-03-09 12:00:00", False),                                                                   # Saturday
    ("2024-03-10 17:59:59", False), ("2024-03-10 18:00:00", True),                                   # Sunday open
])
def test_market_open_follows_the_session_calendar(when, open_):
    d, hms = when.split()
    assert pb.market_open(et(d, hms) // 1_000_000, "NQ") is open_
    assert pb.market_open(et(d, hms) // 1_000_000, "BTC") is True                  # a 24/7 root: always


@pytest.mark.parametrize("why, when, printed_ms", [
    ("the daily break", "2024-03-05 17:30:00", 1000),
    ("Friday after the close", "2024-03-08 17:30:00", 1000),
    ("Saturday", "2024-03-09 12:00:00", 1000),
    ("a halt: no print in 30 s", "2024-03-05 10:00:00", 30_001),
    ("no print yet", "2024-03-05 10:00:00", None),
    ("a print over 1 s ahead of the clock", "2024-03-05 10:00:00", -1001),
])
def test_no_instant_fill_while_the_market_is_not_matching(why, when, printed_ms):
    d, hms = when.split()
    now = et(d, hms)
    b, _ = live(quote=q_(now_ms=now // 1_000_000), depth=l2(now_ms=now // 1_000_000), clock_ns=now,
                printed_ms=printed_ms)
    assert order(b, "Buy", "Market")["ok"]
    assert fills(b) == [] and [o["type"] for o in b.view()["orders"]] == ["Market"]   # it waits for a print


def test_the_print_age_limit_is_inclusive_and_a_24_7_root_trades_on_saturday():
    b, _ = live(quote=q_(), depth=l2(), printed_ms=30_000)
    order(b, "Buy", "Market")
    assert b.fills[-1]["src"] == "book"
    sat = et("2024-03-09", "12:00:00")
    c, _ = live(quote=q_(bid=60000.0, ask=60005.0, now_ms=sat // 1_000_000), root="BTC", clock_ns=sat, px=60005.0)
    order(c, "Buy", "Market", root="BTC")                          # BTC's tick is 5.0
    assert (c.fills[-1]["src"], c.fills[-1]["price"]) == ("quote", 60005.0)


def test_a_pre_open_book_never_fills_a_paper_order():
    """ES, Sunday: the pre-open book was fresh at 7805.75 / 7806.0 and the first print was 7796.0 -- an instant buy
    would have been down $500 on its first tick. It waits for that print instead."""
    now = et("2024-03-10", "17:59:50")
    q = q_(bid=7805.75, ask=7806.0, now_ms=now // 1_000_000)
    depth = l2(bids=((7805.75, 3),), offers=((7806.0, 4),), now_ms=now // 1_000_000)
    b, _ = live(quote=q, depth=depth, root="ES", clock_ns=now, printed_ms=None)
    assert order(b, "Buy", "Market", root="ES")["ok"] and fills(b) == []
    b.on_print("ES", et("2024-03-10", "18:00:00") + 500_000_000, 7796.0)
    assert fills(b) == [("Buy", 1, 7796.25)] and b.fills[-1]["src"] == "print"


def test_a_market_buy_fills_at_once_at_the_ask_and_a_sell_at_the_bid_with_no_slip():
    b, _ = live(quote=q_(bid=99.75, ask=100.0))                       # no Level 2 book: the trade-row quote
    r = order(b, "Buy", "Market", qty=2)                             # no print needed: the quote is the price
    assert r["ok"] and fills(b) == [("Buy", 2, 100.0)] and net(b) == 2 and b.view()["orders"] == []
    f = b.fills[-1]
    assert (f["src"], f["order_id"], f["time"]) == ("quote", r["order_id"], pb._iso(T0 - 500_000_000)) and "parts" not in f
    order(b, "Sell", "Market", qty=2)
    assert fills(b)[-1] == ("Sell", 2, 99.75) and net(b) == 0
    assert b.realized == pytest.approx(-0.25 * 20 * 2 - 8.0)         # the spread, once; $4 a round turn per contract


@pytest.mark.parametrize("why, quote", [
    ("older than 2 s", q_(age_ms=2001)),
    ("over 1 s ahead of the book's clock", q_(age_ms=-1001)),
    ("none", None),
    ("crossed", q_(bid=100.25, ask=100.0)),
    ("locked", q_(bid=100.0, ask=100.0)),
    ("off the tick grid", q_(bid=99.8)),
    ("21 ticks wide", q_(bid=94.75)),
    ("no bid", q_(bid=None)),
    ("not a number", q_(bid=float("nan"))),
    ("no time", {k: v for k, v in q_().items() if k != "ts_ms"}),
    ("no size at the touch", q_(ask_size=None)),
    ("less size at the touch than the order", q_(ask_size=1)),
    ("no trade price", q_(trade=None)),
    ("a trade off the grid", q_(trade=100.1)),
])
def test_with_no_book_an_unusable_quote_leaves_a_market_order_to_the_next_print(why, quote):
    b, _ = live(quote=quote)
    feed(b, [("09:29:59", 100.0)])
    assert order(b, "Buy", "Market", qty=2)["ok"]
    assert fills(b) == [] and [o["type"] for o in b.view()["orders"]] == ["Market"]
    feed(b, [("09:30:01", 100.5)])
    assert fills(b) == [("Buy", 2, 100.75)] and b.fills[-1]["src"] == "print"   # the engine's law: print + 1 tick


def test_the_quote_prices_conservatively_against_its_rows_own_trade():
    """A row whose trade went through its own touch has likely moved it: a buy pays max(ask, trade), a sell gets
    min(bid, trade); a trade inside the spread never improves either."""
    for side, trade, want in (("Buy", 100.5, 100.5), ("Buy", 99.75, 100.0), ("Sell", 99.5, 99.5), ("Sell", 100.0, 99.75)):
        b, _ = live(quote=q_(bid=99.75, ask=100.0, trade=trade))
        order(b, side, "Market", qty=2)
        assert (b.fills[-1]["src"], b.fills[-1]["price"]) == ("quote", want), (side, trade)


def test_the_quote_limits_are_inclusive_and_the_grid_check_is_epsilon_tolerant():
    for quote in (q_(age_ms=2000), q_(age_ms=-1000), q_(bid=95.0), q_(ask_size=2)):   # 2 s old, 1 s ahead, 20 ticks
        b, _ = live(quote=quote)                                                      # wide, the order's size shown
        order(b, "Buy", "Market", qty=2)
        assert fills(b) == [("Buy", 2, 100.0)] and b.fills[-1]["src"] == "quote", quote
    c, _ = live(quote=q_(bid=64.01, ask=64.01 + 0.01), root="CL", px=64.02)
    order(c, "Buy", "Market", root="CL")                             # 64.02000000000001 is on the grid
    assert fills(c) == [("Buy", 1, 64.02)]


def test_a_market_order_walks_the_live_book_for_all_of_its_size_at_the_weighted_average():
    b, _ = live(quote=q_(), depth=l2())
    r = order(b, "Buy", "Market", qty=3)                             # offers 100 x1, 100.25 x1, 100.5 x5
    f = b.fills[-1]
    assert (f["src"], f["qty"], f["price"], f["parts"]) == ("book", 3, 100.25, [[100.0, 1], [100.25, 1], [100.5, 1]])
    assert f["order_id"] == r["order_id"] and b.pos["NQ"]["avg"] == 100.25 and b.view()["orders"] == []
    order(b, "Sell", "Market", qty=4)                                # bids 99.75 x2, 99.5 x1, 99.25 x3
    f = b.fills[-1]
    assert (f["src"], f["price"], f["parts"]) == ("book", 99.5625, [[99.75, 2], [99.5, 1], [99.25, 1]])
    assert net(b) == -1 and b.pos["NQ"]["avg"] == 99.5625            # 3 closed, 1 opened short at the fill
    assert b.realized == pytest.approx((99.5625 - 100.25) * 20 * 3 - 12.0)   # no slip; $4 a contract a round turn


def test_a_fresh_book_too_thin_for_all_of_it_is_the_next_print_never_an_older_quote():
    thin = l2(offers=((100.0, 1), (100.25, 2)))                      # 3 lots on show, 300 ms old
    b, src = live(quote=q_(ask_size=5, age_ms=500), depth=thin)       # an OLDER quote that shows 5 at its touch
    order(b, "Buy", "Market", qty=4)
    assert fills(b) == [] and [o["type"] for o in b.view()["orders"]] == ["Market"]   # never 3 now and 1 later either
    b.on_print("NQ", T0 + 1_000_000_000, 100.5)
    assert fills(b) == [("Buy", 4, 100.75)] and b.fills[-1]["src"] == "print"


def test_the_newer_of_the_book_and_the_quote_decides_and_a_tie_is_the_book():
    deep = l2(offers=((100.0, 1), (100.25, 1), (100.5, 5)))           # 300 ms old
    b, src = live(quote=q_(ask=100.25, bid=100.0, age_ms=100), depth=deep)   # a NEWER quote: its touch, not the book
    order(b, "Buy", "Market", qty=2)
    assert (b.fills[-1]["src"], b.fills[-1]["price"]) == ("quote", 100.25)
    src["quote"] = q_(ask=100.25, bid=100.0, age_ms=100, ask_size=1)    # ...and its touch too small: the next print,
    order(b, "Buy", "Market", qty=2)                                   # not the older book
    assert len(b.fills) == 1 and [o["type"] for o in b.view()["orders"]] == ["Market"]
    c, _ = live(quote=q_(ask=100.25, bid=100.0, age_ms=300), depth=deep)   # the same time: the book
    order(c, "Buy", "Market", qty=2)
    assert (c.fills[-1]["src"], c.fills[-1]["parts"]) == ("book", [[100.0, 1], [100.25, 1]])


@pytest.mark.parametrize("why, depth", [
    ("none", None),
    ("older than 2 s", l2(age_ms=2001)),
    ("over 1 s ahead of the book's clock", l2(age_ms=-1001)),
    ("no time", {"bids": [[99.75, 2]], "offers": [[100.0, 5]]}),
    ("one-sided", l2(bids=())),
    ("crossed", l2(bids=((100.25, 1),))),
    ("locked", l2(bids=((100.0, 1),))),
    ("21 ticks wide", l2(bids=((94.75, 1),))),
    ("a level off the grid", l2(offers=((100.0, 1), (100.3, 5)))),
    ("out of order past what it takes", l2(offers=((100.0, 1), (100.5, 1), (100.25, 5)))),   # fail closed: all of it
    ("a level twice", l2(offers=((100.0, 1), (100.0, 5)))),
    ("a fractional size", l2(offers=((100.0, 1.5), (100.25, 5)))),
    ("a level that is not [price, size]", l2(offers=((100.0, 1), (100.25, 5), (100.5,)))),
])
def test_an_unusable_book_leaves_the_quote(why, depth):
    b, _ = live(quote=q_(), depth=depth)
    order(b, "Buy", "Market", qty=2)
    assert fills(b) == [("Buy", 2, 100.0)] and b.fills[-1]["src"] == "quote"


def test_a_level_priced_at_zero_or_over_40_ticks_from_the_touch_ends_the_walk():
    far = l2(offers=((100.0, 1), (100.25, 1), (110.25, 5)))          # 110.25: 41 ticks from the 100.0 touch
    b, _ = live(quote=q_(age_ms=900), depth=far)
    order(b, "Buy", "Market", qty=3)
    assert fills(b) == [] and [o["type"] for o in b.view()["orders"]] == ["Market"]   # 2 before it: the next print
    order(b, "Buy", "Market", qty=2)                                  # what is before it is enough for 2
    assert b.fills[-1]["parts"] == [[100.0, 1], [100.25, 1]]
    c, _ = live(depth=l2(offers=((100.0, 1), (100.25, 1), (110.0, 5))))   # 40 ticks: still walked
    order(c, "Buy", "Market", qty=3)
    assert c.fills[-1]["parts"] == [[100.0, 1], [100.25, 1], [110.0, 1]]
    for zero in (0.0, -0.25):                                         # a bid at or below 0 (within 40 ticks here)
        d, _ = live(depth=l2(bids=((5.0, 1), (zero, 5)), offers=((5.25, 5),)), px=5.0)
        order(d, "Sell", "Market", qty=2)
        assert fills(d) == [] and [o["type"] for o in d.view()["orders"]] == ["Market"]


def test_an_instant_fill_is_stamped_at_its_sources_time_never_before_the_last_print(tmp_path):
    b, src = live(quote=q_(age_ms=500), depth=l2(age_ms=300), printed_ms=1000, tmp_path=tmp_path)
    order(b, "Buy", "Market")
    last = T0 - 100_000_000 - 123                                             # then a print newer than both, to the ns
    b.on_print("NQ", last, 100.0)
    src["book"] = None
    order(b, "Buy", "Market")                                                 # (the quote, now)
    fills_logged = [e for e in map(json.loads, (tmp_path / "paper" / "book.jsonl").read_text().splitlines())
                    if e["ev"] == "fill"]
    assert [(e["src"], e["ts_ns"]) for e in fills_logged] == [("book", T0 - 300_000_000), ("quote", last)]
    c, _ = live(depth=l2(age_ms=300), printed_ms=100)
    order(c, "Sell", "Market", sl=100.5)                                      # stamped at the print, 100 ms before
    c.on_print("NQ", T0 - 50_000_000, 100.5)                                  # its stop, on the next print
    assert [f["role"] for f in c.fills] == ["entry", "sl"]
    assert [f["time"] for f in c.fills] == [pb._iso(T0 - 100_000_000), pb._iso(T0 - 50_000_000)]   # in order


def test_the_book_limits_are_inclusive():
    for depth in (l2(age_ms=2000), l2(age_ms=-1000), l2(bids=((95.0, 1),))):   # 2 s old, 1 s ahead, 20 ticks wide
        b, _ = live(depth=depth)
        order(b, "Buy", "Market", qty=2)
        assert (b.fills[-1]["src"], b.fills[-1]["parts"]) == ("book", [[100.0, 1], [100.25, 1]]), depth


def test_only_a_market_order_fills_at_once():
    b, _ = live(quote=q_(), depth=l2())
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Limit", price=100.25)                           # through the ask: still waits for a print
    order(b, "Buy", "Stop", price=100.25)
    order(b, "Buy", "StopLimit", price=100.5, trigger=100.25)
    assert fills(b) == [] and len(b.view()["orders"]) == 3


def test_an_entry_filled_at_once_has_its_bracket_live_and_trading_from_the_next_print():
    b, _ = live(quote=q_(), depth=l2())
    feed(b, [("09:29:59", 100.0)])                                   # a Market's bracket is checked against it
    assert order(b, "Buy", "Market", qty=2, sl=99.0, tp=101.0)["ok"]
    assert fills(b) == [("Buy", 2, 100.125)] and b.fills[-1]["src"] == "book"
    assert sorted((o["type"], o["role"], o["status"]) for o in b.view()["orders"]) == \
        [("Limit", "tp", "Working"), ("Stop", "sl", "Working")]      # never "Suspended": the entry is in
    feed(b, [("09:30:01", 99.0)])                                    # the very next print touches the stop
    assert fills(b)[-1] == ("Sell", 2, 98.75) and net(b) == 0 and b.view()["orders"] == []   # its OCO twin went too


def test_flatten_walks_the_book_and_a_reverse_takes_both_legs_from_one_read():
    b, src = live(quote=q_(), depth=l2())
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market", qty=3, sl=95.0, tp=110.0)              # in at 100.25 (the book)
    src["book"] = l2(bids=((101.0, 2), (100.75, 5)), offers=((101.25, 1), (101.5, 1), (102.0, 9)))
    assert act(b, "flatten", accounts=[PAPER_ID], root="NQ")["ok"]
    f = b.fills[-1]
    assert net(b) == 0 and b.view()["orders"] == [] and (f["side"], f["qty"], f["parts"]) == ("Sell", 3, [[101.0, 2], [100.75, 1]])
    order(b, "Buy", "Market", qty=2)
    assert b.fills[-1]["parts"] == [[101.25, 1], [101.5, 1]]
    src["book"] = l2(bids=((101.0, 2), (100.75, 5)), offers=((101.25, 1), (101.5, 1), (102.0, 9)), age_ms=100)
    # (a new snapshot: all of it on show again) a reverse reads the book ONCE, for 4: the close takes the first 2 of
    # it, the open the next 2
    assert act(b, "reverse", accounts=[PAPER_ID], root="NQ")["ok"]
    assert [(f["role"], f["price"], f["parts"]) for f in b.fills][-2:] == \
        [("flat", 101.0, [[101.0, 2]]), ("entry", 100.75, [[100.75, 2]])]
    assert net(b) == -2 and b.pos["NQ"]["avg"] == 100.75 and b.view()["orders"] == []
    # short 2: a buy reverse needs 4 -- the book shows 3 and the quote's touch 3: both legs wait, in order
    src["book"], src["quote"] = l2(offers=((100.5, 3),)), q_(ask=100.0, ask_size=3)
    assert act(b, "reverse", accounts=[PAPER_ID], root="NQ")["ok"]
    assert [o["type"] for o in b.view()["orders"]] == ["Market", "Market"] and net(b) == -2
    feed(b, [("09:30:01", 100.5)])
    assert net(b) == 2 and [f["src"] for f in b.fills][-2:] == ["print", "print"]
    src["book"], src["quote"] = None, q_(bid_size=4)                 # no book, the quote's bid shows 4: both at it
    assert act(b, "reverse", accounts=[PAPER_ID], root="NQ")["ok"]
    assert [(f["role"], f["price"], f["src"]) for f in b.fills][-2:] == [("flat", 99.75, "quote"), ("entry", 99.75, "quote")]


def test_the_book_is_consumed_what_one_order_took_the_next_walks_past():
    b, src = live(depth=l2(bids=((99.75, 4),), offers=((100.0, 2), (100.25, 3), (100.5, 2))))
    order(b, "Buy", "Market", qty=3)
    order(b, "Buy", "Market", qty=3)                                 # the same snapshot: what the first left
    assert [f["parts"] for f in b.fills] == [[[100.0, 2], [100.25, 1]], [[100.25, 2], [100.5, 1]]]
    order(b, "Sell", "Market", qty=4)                                # the other side is its own
    assert b.fills[-1]["parts"] == [[99.75, 4]]
    order(b, "Buy", "Market", qty=2)                                 # 1 left on show: never a part -- the next print
    assert len(b.fills) == 3 and [o["type"] for o in b.view()["orders"]] == ["Market"]
    act(b, "cancel-symbol", accounts=[PAPER_ID], root="NQ")
    src["book"] = l2(bids=((99.75, 4),), offers=((100.0, 2), (100.25, 3), (100.5, 2)), age_ms=100)   # a new snapshot
    order(b, "Buy", "Market", qty=2)                                 # ...starts over
    assert b.fills[-1]["parts"] == [[100.0, 2]]


def test_a_send_to_several_accounts_is_one_plan_each_taking_its_slice_in_order(tmp_path):
    src = {"book": l2(offers=((100.0, 1), (100.25, 2), (100.5, 5)), age_ms=0)}
    bs = pb.PaperBooks(tmp_path / "paper", roots=["NQ"], clock_ms=lambda: NOW_MS, book_of=lambda r: src["book"])
    bs.create({"name": "Two"})
    bs.create({"name": "Three"})
    feed_all(bs, [("09:29:59", 100.0)])
    assert all(r["ok"] for r in bs_order(bs, ["paper", "paper-2", "paper-3"], qty=2).values())   # one plan, for 6
    assert [bs.books[a].fills[-1]["parts"] for a in ("paper", "paper-2", "paper-3")] == \
        [[[100.0, 1], [100.25, 1]], [[100.25, 1], [100.5, 1]], [[100.5, 2]]]
    bs_order(bs, ["paper", "paper-2"], qty=2)                        # 4 wanted, 2 left on show: neither fills now
    assert [[o["type"] for o in bs.books[a].view()["orders"]] for a in ("paper", "paper-2")] == [["Market"], ["Market"]]
    for a in ("paper", "paper-2"):
        bs.books[a].act("cancel-symbol", {"client_id": f"x{a}", "accounts": [a], "root": "NQ"})
    for px, n in ((90.0, 10), (91.0, 8)):                            # paper-2 (long 2): 18 more working on the buy side
        assert bs.books["paper-2"].act("order", {"client_id": f"l{px}", "accounts": ["paper-2"], "root": "NQ",
                                                 "side": "Buy", "type": "Limit", "price": px, "qty": n})["results"]["paper-2"]["ok"]
    src["book"] = l2(offers=((100.0, 1), (100.25, 2)), age_ms=-1)     # a new snapshot
    res = bs_order(bs, ["paper", "paper-2", "paper-3"], qty=1)        # paper-2 would pass 20: refused -- its slice
    assert res["paper-2"]["refused"] and res["paper"]["ok"] and res["paper-3"]["ok"]   # goes to the next in line
    assert (bs.books["paper"].fills[-1]["parts"], bs.books["paper-3"].fills[-1]["parts"]) == ([[100.0, 1]], [[100.25, 1]])
    bs_order(bs, ["paper"], qty=1)                                   # the slice no one took is still there
    assert bs.books["paper"].fills[-1]["parts"] == [[100.25, 1]]


def test_an_instant_fill_is_logged_with_its_src_and_levels_and_survives_a_restart(tmp_path):
    b, _ = live(quote=q_(), depth=l2(), tmp_path=tmp_path)
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "Market", qty=2, sl=98.0)
    log = [json.loads(x) for x in (tmp_path / "paper" / "book.jsonl").read_text().splitlines()]
    assert [e["ev"] for e in log] == ["place", "fill"]
    assert {k: log[1][k] for k in ("price", "ts_ns", "src", "parts")} == \
        {"price": 100.125, "ts_ns": (NOW_MS - 300) * 1_000_000, "src": "book", "parts": [[100.0, 1], [100.25, 1]]}
    again = book(tmp_path)                                           # a restart replays the log: no book needed
    f = again.fills[-1]
    assert (net(again), again.pos["NQ"]["avg"], f["src"], f["parts"]) == (2, 100.125, "book", [[100.0, 1], [100.25, 1]])
    assert [(o["role"], o["status"]) for o in again.view()["orders"]] == [("sl", "Working")]
    old = tmp_path / "old" / "paper" / "book.jsonl"                  # a log from before `src`: its fills were prints
    old.parent.mkdir(parents=True)
    old.write_text("".join(json.dumps({k: v for k, v in e.items() if k not in ("src", "parts")}) + "\n" for e in log))
    f = book(tmp_path / "old").fills[-1]
    assert f["src"] == "print" and "parts" not in f


def test_every_paper_account_fills_at_once_and_each_change_is_announced(tmp_path):
    src, changed = {"quote": q_(age_ms=0), "book": None}, []
    bs = pb.PaperBooks(tmp_path / "paper", roots=["NQ"], clock_ms=lambda: NOW_MS, quote_of=lambda r: src["quote"],
                       book_of=lambda r: src["book"], on_change=lambda: changed.append(1))
    bs.create({"name": "Two"})
    assert len(changed) == 1
    bs.message()
    feed_all(bs, [("09:29:59", 100.0)])                              # the market is matching: a print, no change
    assert len(changed) == 1
    res = bs_order(bs, ["paper", "paper-2"])
    assert all(r["ok"] for r in res.values()) and len(changed) == 2            # one announcement per action
    assert [b.fills[-1]["price"] for b in bs.books.values()] == [100.0, 100.0]
    src["book"] = l2(age_ms=0)
    bs_order(bs, ["paper-2"], qty=2)
    assert bs.books["paper-2"].fills[-1]["parts"] == [[100.0, 1], [100.25, 1]] and len(changed) == 3
    bs.message()                                                    # pushed: nothing is dirty now
    feed_all(bs, [("09:30:01", 100.0)])                              # a print that changes nothing: silent
    assert bs_order(bs, ["paper"], qty=11)["paper"]["refused"]       # a refusal changes nothing: silent
    assert len(changed) == 3
    src["quote"] = src["book"] = None
    bs_order(bs, ["paper"], side="Sell")                            # nothing to fill at: placed, waiting -- a change
    bs.message()
    feed_all(bs, [("09:30:02", 100.5)])                              # the print that fills it -- a change
    assert len(changed) == 5 and bs.books["paper"].fills[-1]["src"] == "print"


def test_a_paper_change_reaches_the_page_at_once_without_waiting_for_the_pump(tmp_path, monkeypatch):
    """The pump stopped (PUMP_S an hour): the PAPER accounts still reach the page at once -- after a POST and after
    the print that fills -- and a fresh quote fills a Market on the spot, at the bid."""
    monkeypatch.setattr(server, "PUMP_S", 3600.0)
    with TestClient(live_app(tmp_path), base_url=BASE_URL) as c, c.websocket_connect("/ws", headers=WS_HOST) as ws:
        assert next_within(ws, "paperbook")["accounts"][0]["orders"] == []          # the greeting
        buy = {"client_id": "f1", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        assert c.post("/api/paper/order", json=buy).json()["results"][PAPER_ID]["ok"]   # no quote yet: it waits
        assert [o["type"] for o in next_within(ws, "paperbook")["accounts"][0]["orders"]] == ["Market"]
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(CD, 9, 44, 59), [101.0])))  # bid 100.75 / ask 101, 1 s old
        a = next_within(ws, "paperbook", lambda m: m["accounts"][0]["positions"])["accounts"][0]
        assert (a["fills"][-1]["price"], a["fills"][-1]["src"]) == (101.25, "print")
        sell = {**buy, "client_id": "f2", "side": "Sell"}
        assert c.post("/api/paper/order", json=sell).json()["results"][PAPER_ID]["ok"]
        a = next_within(ws, "paperbook", lambda m: not m["accounts"][0]["positions"])["accounts"][0]
        assert a["orders"] == [] and \
            (a["fills"][-1]["side"], a["fills"][-1]["price"], a["fills"][-1]["src"]) == ("Sell", 100.75, "quote")


def test_the_service_walks_its_own_live_level2_book(tmp_path):
    """End to end: the chart service's Depth (a fake md socket, one DOM push as Tradovate sends it) is the book a
    PAPER market order walks."""
    from tests.test_charts_depth import NQ as NQ_CONTRACT, FakeWS, subs
    from tests.test_charts_depth_server import LiveFeed, wait_for
    class TickingFeed(LiveFeed):                                    # ...that also delivers the prints it is given
        def __call__(self, roots, on_ticks, on_subscribed=None):
            self.on_ticks = on_ticks
            return super().__call__(roots, on_ticks, on_subscribed)

    ws = FakeWS()
    live_feed = TickingFeed(ws)
    app = create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=live_feed,
                     now_ms=lambda: session_ms(CD, 9, 45), state=tmp_path / "state",
                     depth_roots=("NQ",), depth_base=tmp_path / "depth")
    with TestClient(app, base_url=BASE_URL) as c:
        wait_for(lambda: subs(ws) == [NQ_CONTRACT] and c.get("/api/status").json()["depth"]["NQ"]["subscribed"])
        live_feed.q.put(lambda: live_feed.on_ticks("NQ", "NQZ6", rows(session_ms(CD, 9, 44, 59), [100.0])))  # matching
        live_feed.q.put(lambda: ws.push(111, [(99.75, 2)], [(100.0, 1), (100.25, 4)]))   # stamped at the clock
        wait_for(lambda: c.get("/api/status").json()["depth"]["NQ"]["levels"] == [1, 2])
        body = {"client_id": "l2", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 3, "type": "Market"}
        assert c.post("/api/paper/order", json=body).json()["results"][PAPER_ID]["ok"]
        f = c.get("/api/paper/book").json()["accounts"][0]["fills"][-1]
    assert (f["src"], f["qty"], f["price"], f["parts"]) == ("book", 3, 100.166667, [[100.0, 1], [100.25, 2]])
