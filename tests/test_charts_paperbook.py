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
from homebase.charts.desk import DeskLink
from homebase.charts.paperbook import PAPER_ID, PaperBook
from homebase.charts.server import create_app
from tests.charts_util import D as CD, rows, session_ms
from tests.test_backtest_engine import D, Script, tape
from tests.test_charts_desk_server import BASE_URL, WS_HOST, QuietFeed, key_file, live_app
from tests.test_charts_server import archive, next_of

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
    assert [o["type"] for o in b.view()["orders"]] == ["Stop"]          # the legs wait on their entry
    feed(b, [("09:30:01", 104.0)])                                      # entry through the TP level: TP not live yet
    assert fills(b) == [("Buy", 1, 104.25)] and net(b) == 1
    assert sorted((o["type"], o["role"]) for o in b.view()["orders"]) == [("Limit", "tp"), ("Stop", "sl")]
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


def test_a_stop_limit_triggers_on_touch_then_rests_as_a_limit_from_the_next_print():
    b = book()
    feed(b, [("09:29:59", 100.0)])
    order(b, "Buy", "StopLimit", price=101.5, trigger=101.0)
    feed(b, [("09:30:01", 101.0)])                       # triggered, never filled on its trigger print
    assert fills(b) == []
    feed(b, [("09:30:02", 101.5)])                       # at the limit: no penetration
    assert fills(b) == []
    feed(b, [("09:30:03", 101.25)])
    assert fills(b) == [("Buy", 1, 101.5)]


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
        assert first["account"]["id"] == PAPER_ID and first["account"]["env"] == "paper"
        assert first["limits"] == {"max_order_qty": 10, "max_position_qty": 20}
        body = {"client_id": "p1", "accounts": [PAPER_ID], "root": "NQ", "side": "Buy", "qty": 1, "type": "Market"}
        r = c.post("/api/paper/order", json=body)
        assert r.status_code == 200 and r.json()["results"][PAPER_ID]["ok"] is True
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(CD, 9, 41), [101.0])))   # the next print fills it
        for _ in range(10):
            m = next_of(ws, "paperbook", limit=50)
            if m["account"]["positions"]:
                break
        assert m["account"]["positions"][0]["net"] == 1 and m["account"]["fills"][0]["price"] == 101.25
        assert c.get("/api/paper/book").json()["account"]["positions"][0]["avg_price"] == 101.25
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
