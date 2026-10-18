"""The server's breakeven / trailing-stop runner (the owner, 2026-10-18).

The order panel arms a breakeven ("be": once the last trade reaches `level`, the stop goes to entry + 1 tick) or a
trailing stop ("trail": the stop follows the best price since the fill at `dist` ticks, in trail_step(dist) steps)
with the order it sends. With "Runs on: the server" the arm lives HERE, in the chart service -- the process that has
the live prices -- so it keeps working with the page or the browser closed (static/charts/orderpanel.js keeps its own
arms otherwise; the rules are the same as HBTrade.beArmStep / stopTo / trailStop).

Each arm is checked every POLL_S against the latest fresh trade and every armed account's position and orders (the
desk's account views and the PAPER books', one shape). A stop is moved through the desk's own `modify` (every order
of the account's one stop price) or added through its `exits`; the desk and the paper book keep every check they
make for a page's request (lock, gates, the stop-side check against the attached quotes). A stop is never loosened.
Each account's breakeven fires once; an arm drops when its position is gone, when 15 s after the send there is
neither a position nor an order, and after 8 hours whatever happened. Arms are saved to a file and survive a restart.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import time
from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException, Request

from .. import netguard
from ..contracts import root_of, round_to_tick, tick_size

KINDS = ("be", "trail")
POLL_S = 0.5
GRACE_S = 15.0            # after the send: no position and no order by then = refused / cancelled
MAX_AGE_S = 8 * 3600.0    # an arm never outlives a trading day's session
MOVE_GAP_S = 2.0          # a trail's moves at most this often (the last one is still landing)
QUOTE_MAX_AGE_S = 10.0
MAX_ARMS = 50


def trail_step(dist: int) -> int:
    return max(1, round(dist / 5))


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def parse_arm(body) -> dict:
    """{kind, root, side, accounts, level (be) | dist (trail), be_id?}: what a page may arm."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    kind, root, side = body.get("kind"), body.get("root"), body.get("side")
    if kind not in KINDS:
        raise ValueError("kind: be or trail")
    if not isinstance(root, str) or not root.isalnum() or not 1 <= len(root) <= 6:
        raise ValueError("root: a symbol root such as NQ")
    if side not in ("Buy", "Sell"):
        raise ValueError("side: Buy or Sell")
    acc = body.get("accounts")
    if not isinstance(acc, list) or not 1 <= len(acc) <= 20 or not all(isinstance(a, str) and 1 <= len(a) <= 64 for a in acc):
        raise ValueError("accounts: a list of 1-20 account ids")
    arm = {"kind": kind, "root": root.upper(), "side": side, "accounts": list(dict.fromkeys(acc))}
    if kind == "be":
        if not _finite(body.get("level")):
            raise ValueError("level: the breakeven price")
        arm["level"] = float(body["level"])
    else:
        d = body.get("dist")
        if isinstance(d, bool) or not isinstance(d, int) or not 1 <= d <= 100000:
            raise ValueError("dist: the trail's distance in whole ticks")
        arm["dist"] = d
        b = body.get("be_id")
        if b is not None and (not isinstance(b, str) or len(b) > 64):
            raise ValueError("be_id: the breakeven arm it waits for")
        arm["be_id"] = b
    return arm


def _order_price(o: dict):
    if "stop" in str(o.get("type") or "").lower():
        return o.get("stop_price") if o.get("stop_price") is not None else o.get("price")
    return o.get("price") if o.get("price") is not None else o.get("stop_price")


def _pending(o: dict) -> bool:
    return o.get("status") is not None and o.get("status") != "Working"


def account_state(view: dict, root: str) -> dict:
    """One account in one root: its signed net, average price, and its own (not a bot's) orders."""
    pos = [p for p in (view.get("positions") or []) if p.get("root") == root and p.get("net")]
    net = sum(int(p["net"]) for p in pos)
    avg = (sum(float(p["avg_price"]) * abs(int(p["net"])) for p in pos) / sum(abs(int(p["net"])) for p in pos)) if pos else None
    orders = [o for o in (view.get("orders") or [])
              if not o.get("owner") and o.get("symbol") and root_of(o["symbol"]) == root]
    return {"net": net, "avg": avg, "orders": orders}


def stop_plan(side: str, orders: list, price: float, step: int, tick: float) -> tuple:
    """The account's stop to `price`: ('move', [order ids]) -- every order at its one stop price --, ('add', []),
    ('none', []) unless that tightens it by `step` ticks (never loosened), or ('error', why)."""
    if any(_pending(o) for o in orders):
        return "error", "an order on this position is still pending"
    exit_side = "Sell" if side == "Buy" else "Buy"
    sls = [o for o in orders if o.get("side") == exit_side and "stop" in str(o.get("type") or "").lower()]
    if not sls:
        return "add", []
    prices = {_order_price(o) for o in sls}
    if len(prices) != 1 or not _finite(next(iter(prices))):
        return "error", "this position has stops at different prices"
    cur = float(next(iter(prices)))
    gain = ((price - cur) if side == "Buy" else (cur - price)) / tick
    return ("move", [str(o.get("order_id")) for o in sls]) if gain >= step - 1e-9 else ("none", [])


def arm_step(arm: dict, views: dict, last: Optional[float], now: float, armed_ids=frozenset()) -> tuple:
    """One look at one arm (updates its `seen` / `best` in place): ('drop', why) | ('wait', None) |
    ('act', [{account, net, price, plan, ids}]). The caller sends the acts and marks them (done / sent_at)."""
    if now - arm["at"] > MAX_AGE_S:
        return "drop", "expired"
    root, side = arm["root"], arm["side"]
    s = 1 if side == "Buy" else -1
    accts = {aid: account_state(views.get(aid) or {}, root) for aid in arm["accounts"]}
    held = {aid: st for aid, st in accts.items() if st["net"] * s > 0}
    if not held:
        if arm.get("seen"):
            return "drop", "flat"
        working = any(st["orders"] for st in accts.values())
        return ("wait", None) if working or now - arm["at"] < GRACE_S else ("drop", "no order")
    arm["seen"] = True
    if not _finite(last):
        return "wait", None
    tick = tick_size(root)
    acts = []
    if arm["kind"] == "be":
        if not (last >= arm["level"] if s > 0 else last <= arm["level"]):
            return "wait", None
        for aid, st in held.items():
            if aid in arm.setdefault("done", []):
                continue
            price = round_to_tick(root, st["avg"] + s * tick)
            plan, ids = stop_plan(side, st["orders"], price, 1, tick)
            acts.append({"account": aid, "net": st["net"], "price": price, "plan": plan, "ids": ids})
        return ("act", acts) if acts else ("drop", "done")
    best = arm.get("best")
    arm["best"] = last if best is None else (max(best, last) if s > 0 else min(best, last))
    if arm.get("be_id") and arm["be_id"] in armed_ids:
        return "wait", None                                   # "after breakeven": not yet
    if now - arm.get("sent_at", 0) < MOVE_GAP_S:
        return "wait", None
    price = round_to_tick(root, arm["best"] - s * arm["dist"] * tick)
    if (last <= price) if s > 0 else (last >= price):
        return "wait", None                                   # the market is at or through it: a stop there is refused
    for aid, st in held.items():
        plan, ids = stop_plan(side, st["orders"], price, trail_step(arm["dist"]), tick)
        if plan != "none":
            acts.append({"account": aid, "net": st["net"], "price": price, "plan": plan, "ids": ids})
    return ("act", acts) if acts else ("wait", None)


class ExitRunner:
    """The arms, their file, and the loop. `views()` -> {account id: account view} (the desk's and the paper
    books'); `last_of(root)` -> the latest fresh trade or None; `send(action, body)` -> awaitable {"results": ...}
    (the caller routes PAPER accounts to the paper book, the rest to the desk)."""

    def __init__(self, path: Optional[Path], *, views: Callable[[], dict], last_of: Callable[[str], Optional[float]],
                 send: Callable[[str, dict], Awaitable[dict]], clock: Callable[[], float] = time.time,
                 log: Callable[[str], None] = print):
        self.path, self.views, self.last_of, self.send, self.clock, self.log = path, views, last_of, send, clock, log
        self.arms: list[dict] = []
        self._stop = False
        if path is not None and path.exists():
            try:
                data = json.loads(path.read_text())
                self.arms = [a for a in data if isinstance(a, dict) and a.get("kind") in KINDS] if isinstance(data, list) else []
            except (OSError, ValueError) as e:
                log(f"exit runner: {path.name} unreadable ({e}) — starting with no arms")

    def _save(self) -> None:
        if self.path is None:
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.arms))
        tmp.replace(self.path)

    def listing(self) -> list[dict]:
        return [dict(a) for a in self.arms]

    def arm(self, body) -> dict:
        a = parse_arm(body)
        if len(self.arms) >= MAX_ARMS:
            raise ValueError(f"at most {MAX_ARMS} arms at once")
        a.update(id=secrets.token_hex(8), at=self.clock(), seen=False, done=[], sent_at=0, error=None)
        self.arms.append(a)
        self._save()
        return dict(a)

    def cancel(self, aid: str) -> bool:
        n = len(self.arms)
        self.arms = [a for a in self.arms if a["id"] != aid]
        self._save()
        return len(self.arms) != n

    async def _do(self, arm: dict, act: dict) -> None:
        cid = lambda: f"xr-{secrets.token_hex(6)}"   # noqa: E731
        aid, price = act["account"], act["price"]
        if act["plan"] == "move":
            outs = [await self.send("modify", {"client_id": cid(), "account": aid, "order_id": oid, "price": price})
                    for oid in act["ids"]]
        else:
            outs = [await self.send("exits", {"client_id": cid(), "accounts": [aid], "root": arm["root"],
                                              "sl_price": price, "expected_net": {aid: act["net"]}})]
        bad = [r.get("error") for o in outs for r in ((o or {}).get("results") or {}).values() if not r.get("ok")]
        bad += [o.get("detail") for o in outs if o and "detail" in o]
        arm["error"] = "; ".join(str(b) for b in bad if b) or None
        self.log(f"exit runner: {arm['kind']} {arm['root']} {aid} stop -> {price}" + (f" FAILED: {arm['error']}" if arm["error"] else ""))

    async def tick_once(self) -> None:
        if not self.arms:
            return
        views, now, changed = self.views(), self.clock(), False
        armed = frozenset(a["id"] for a in self.arms)
        for arm in list(self.arms):
            before = (arm.get("seen"), arm.get("best"))
            what, acts = arm_step(arm, views, self.last_of(arm["root"]), now, armed)
            changed |= before != (arm.get("seen"), arm.get("best"))
            if what == "drop":
                self.arms.remove(arm)
                changed = True
                continue
            if what != "act":
                continue
            for act in acts:
                if arm["kind"] == "be":
                    arm.setdefault("done", []).append(act["account"])   # each account once, whatever happens next
                if act["plan"] == "error":
                    arm["error"] = act["ids"] if isinstance(act["ids"], str) else "can't move this stop"
                    continue
                if act["plan"] == "none":
                    continue
                arm["sent_at"] = now
                self._save()
                await self._do(arm, act)
            changed = True
        if changed:
            self._save()

    async def run(self) -> None:
        while not self._stop:
            try:
                await self.tick_once()
            except Exception as e:  # noqa: BLE001 — the loop must outlive one bad pass
                self.log(f"exit runner: {type(e).__name__}: {e}")
            await asyncio.sleep(POLL_S)

    def stop(self) -> None:
        self._stop = True


BODY_MAX = 4096
NO_RUNNER = "the server runner is not available here (replay)"


def register(app, *, runner: Optional[ExitRunner], browser_write_ok, allowed: Optional[frozenset] = None) -> None:
    """GET /api/exitrunner -> {arms}; POST /api/exitrunner/arm {kind, root, side, accounts, level | dist, be_id?}
    -> the arm; POST /api/exitrunner/cancel {id} -> {ok}. The desk proxy's guards: the Host / Origin allowlist,
    JSON only, this service's own origin for writes, 4 KB bodies."""
    allowed = netguard.allowlist() if allowed is None else allowed

    def guard(request: Request) -> None:
        bad = netguard.refusal(request.method, request.scope["headers"], allowed)
        if bad is not None:
            raise HTTPException(*bad)
        if runner is None:
            raise HTTPException(503, NO_RUNNER)

    @app.get("/api/exitrunner")
    async def exitrunner_list(request: Request):
        guard(request)
        return {"arms": runner.listing()}

    @app.post("/api/exitrunner/{action}")
    async def exitrunner_act(action: str, request: Request):
        guard(request)
        browser_write_ok(request)
        if action not in ("arm", "cancel"):
            raise HTTPException(404, f"unknown action {action!r}")
        raw = await request.body()
        if len(raw) > BODY_MAX:
            raise HTTPException(413, "request too large (4 KB max)")
        try:
            body = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if action == "cancel":
            if not isinstance(body, dict) or not isinstance(body.get("id"), str):
                raise HTTPException(400, "id: the arm to cancel")
            return {"ok": runner.cancel(body["id"])}
        try:
            return runner.arm(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
