"""The websockets: /ws (every chart page) and /ws/depth-in (the book relay)."""
from __future__ import annotations

import asyncio
import json
import traceback

from fastapi import WebSocket, WebSocketDisconnect

from ... import netguard
from ..bars import BarSpec
from ..hub import Stream
from ..studies import make
from .common import origin_ok

SEND_QUEUE_MAX = 400


class Conn:
    """One browser socket. Sends go through a bounded queue drained by a
    writer task, so one slow page can never stall the pump; a page that
    falls SEND_QUEUE_MAX messages behind is disconnected (it reconnects)."""

    def __init__(self, ws: WebSocket, page: str = "charts"):
        self.ws = ws
        # 2026-09-28 three-tabs plan: which page this socket is (?page=backtest on /ws, "charts" by
        # default) -- lets fan_count target only Backtest-tab connections (show_on_chart).
        self.page = page
        self.q: asyncio.Queue = asyncio.Queue(maxsize=SEND_QUEUE_MAX)
        self.dead = False
        self.task = asyncio.create_task(self._writer())

    def send(self, msg: dict) -> None:
        if self.dead:
            return
        try:
            self.q.put_nowait(msg)
        except asyncio.QueueFull:
            self.dead = True
            self.task.cancel()
            asyncio.create_task(self._close())

    async def _close(self) -> None:
        try:
            await self.ws.close()
        except Exception:  # noqa: BLE001
            pass

    async def _writer(self) -> None:
        try:
            while True:
                await self.ws.send_json(await self.q.get())
        except Exception:  # noqa: BLE001 — socket gone; the handler cleans up
            self.dead = True


def register(app, *, relay, conns, status, paper, desk_fan, book, replays, hub, depth, booklive, tapelive, roots,
             MIN_BAR, MAX_STUDIES, log) -> None:
    older_busy: set = set()     # (conn, chart id, stream identity) with a scroll-back chunk being built --
                                # keyed by the STREAM (not just conn/cid) so a fresh subscription after an
                                # interval switch is never blocked by the old stream's still-running chunk
    older_tasks: set = set()    # the answering tasks, referenced until they finish

    def ask_older(conn: Conn, cid: str, before, fp: bool = True, big: bool = True, flow: bool = True) -> None:
        """A chart scrolled back to its first bar ({"op": "older", "id", "before": that bar's ms}): build the
        next chunk of older sessions off the loop and answer {"type": "older", "id", "before", "bars",
        "studies", "repair", "sessions", "done"}, or with an "error" (the page waits, then may ask again).
        fp / big ("fp"?, "big"? on the request, as on the chart's `sub`): whether the bars carry them.
        One at a time per chart+stream; it never touches the broker. A request that lands while the
        previous one for the same chart+stream is still building answers {"error": "busy"} rather than
        being silently dropped, so the page can retry instead of the chart losing scroll-back forever."""
        s = hub.stream_of((conn, cid))
        if s is None or not isinstance(before, int) or isinstance(before, bool):
            conn.send({"type": "older", "id": cid, "before": before,
                       "error": "not subscribed" if s is None else "before: the first bar's time (epoch ms)"})
            return
        key = (conn, cid, id(s))
        if key in older_busy:
            conn.send({"type": "older", "id": cid, "before": before, "error": "busy"})
            return
        older_busy.add(key)
        task = asyncio.create_task(answer_older(conn, cid, key, s, before, fp, big, flow))
        older_tasks.add(task)
        task.add_done_callback(older_tasks.discard)

    async def answer_older(conn: Conn, cid: str, key: tuple, s: Stream, before: int, fp: bool, big: bool,
                           flow: bool = True) -> None:
        try:
            ans = await asyncio.to_thread(hub.older, s, before, fp, big, flow)
        except Exception as e:  # noqa: BLE001 — a failed chunk is the page's to retry, never the socket's end
            log(f"older {cid} ({s.root} {s.spec.key}): {type(e).__name__}: {e}")
            ans = {"error": str(e) or type(e).__name__}
        finally:
            older_busy.discard(key)
        conn.send({"type": "older", "id": cid, "before": before, **ans})

    @app.websocket("/ws/depth-in")
    async def ws_depth_in(sock: WebSocket):
        """The book relay (depthrelay.py): the Mac's books, into this service's Depth (HOMEBASE_DEPTH_RELAY_IN=1 only).
        Only a local non-browser client (no Origin): the pusher on the Mac, through its ssh tunnel."""
        if relay is None or sock.headers.get("origin") is not None:
            await sock.close(code=1008)
            return
        await sock.accept()
        relay.ws.pushers += 1
        try:
            while True:
                try:
                    relay.ws.push(json.loads(await sock.receive_text()))
                except (WebSocketDisconnect, RuntimeError):
                    raise
                except Exception:  # noqa: BLE001 — a bad frame is skipped
                    continue
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            relay.ws.pushers -= 1

    @app.websocket("/ws")
    async def ws_endpoint(sock: WebSocket):
        if not origin_ok(sock.headers.get("origin"), sock.headers.get("host")):
            await sock.close(code=1008)     # before accept(): the handshake is refused (403)
            return
        if not netguard.host_allowed(sock.headers.get("host"), netguard.allowlist()):
            # origin_ok() alone waves through a DNS-rebinding page: it is
            # served AS the attacker's own hostname, so its Origin and Host
            # both read e.g. evil.example and satisfy origin_ok's Origin==Host
            # rule. This service now carries balances, positions and orders
            # for every account, so the Host header itself must also be on
            # netguard's shared allowlist (loopback only here -- this
            # process has no cfg.allowed_hosts of its own) before the
            # handshake is accepted.
            await sock.close(code=1008)
            return
        await sock.accept()
        page = sock.query_params.get("page", "charts")
        conn = Conn(sock, page=page if page == "backtest" else "charts")
        conns.add(conn)
        conn.send({"type": "status", **status()})
        if paper.current is not None:
            conn.send(paper.current)            # the paper run's state, like every later change
        def room() -> bool:
            return not conn.dead and conn.q.qsize() < SEND_QUEUE_MAX // 2

        desk_fan.attach(conn, conn.send, room)
        if book is not None:
            conn.send(book.message(clear=False))   # the PAPER account as it stands (every other page keeps its update)
        try:
            while True:
                # Only a framing/decoding problem is swallowed here. Receiving
                # itself is NOT wrapped in a broad except: after an app-side
                # close (Conn._close(), on a SEND_QUEUE_MAX overflow), starlette
                # raises WebSocketDisconnect OR a RuntimeError SYNCHRONOUSLY --
                # before any await -- so a broad `except Exception: continue`
                # around the receive call would never yield control back to the
                # loop, spinning it at 100% CPU forever instead of ending here.
                try:
                    raw = await sock.receive_text()
                except (WebSocketDisconnect, RuntimeError):
                    raise
                except Exception:  # noqa: BLE001 — a non-text (binary) frame is skipped
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                op, cid = msg.get("op"), str(msg.get("id", ""))
                if op == "unsub":
                    replays.stop(conn, cid, notify=False)
                    hub.unsubscribe((conn, cid))
                    if depth is not None:
                        depth.unview((conn, cid))
                        booklive.unview((conn, cid))
                    continue
                if op == "older":
                    if not replays.ask_older(conn, cid, msg.get("before")):
                        ask_older(conn, cid, msg.get("before"), bool(msg.get("fp", True)), bool(msg.get("big", True)),
                                  bool(msg.get("flow", True)))
                    continue
                if op == "replay_start":
                    if await replays.start(conn, cid, msg, live=hub.stream_of((conn, cid))):
                        hub.unsubscribe((conn, cid))    # the chart leaves the live stream
                    continue
                if op == "replay_ctl":
                    await replays.control(conn, cid, msg)
                    continue
                if op == "replay_stop":
                    replays.stop(conn, cid)
                    continue
                if op == "tape":
                    # the Time & Sales panel follows one root per page; null or an uncharted root closes it
                    root = str(msg.get("root") or "").upper()
                    if root in roots:
                        tapelive.view((conn, "tape"), root, conn.send, room)
                    else:
                        tapelive.unview((conn, "tape"))
                    continue
                if op != "sub":
                    continue
                try:
                    root = str(msg.get("root", "")).upper()
                    if root not in roots:
                        raise ValueError(f"{root!r} is not recorded (have {', '.join(roots)})")
                    spec = BarSpec.parse(msg.get("spec", ""))
                    if spec.size < MIN_BAR[spec.kind]:
                        raise ValueError(f"{spec.key} is too fine for the live charts "
                                         f"(minimum {spec.kind}:{MIN_BAR[spec.kind]})")
                    studies = msg.get("studies") or []
                    if len(studies) > MAX_STUDIES:
                        raise ValueError(f"{len(studies)} studies on one chart (at most {MAX_STUDIES})")
                    keys = [str(k) for k in studies]
                    for k in keys:
                        if k != "profile":
                            make(k)     # ValueError on an unknown study or a length outside 1..1000
                except Exception as e:  # noqa: BLE001 — a malformed sub (bad root/spec/study, too
                                        # fine, too many) answers an error, never kills the connection
                    conn.send({"type": "error", "id": cid, "error": str(e)})
                    continue
                s = None
                replays.stop(conn, cid, notify=False)   # a sub on a replaying chart returns it to live
                try:
                    # An indicator added is this same chart asking again for the same market and interval with one
                    # more study: its stream is kept (not rebuilt from every session, 1-4 s on a cold 5m..1D chart)
                    # and only the new study is run over it. A stream marked for reset is never reused.
                    same = hub.streams.get((root, spec.key))
                    hub.unsubscribe((conn, cid), keep=same if same is not None and not same.reset else None)
                    s = hub.streams.get((root, spec.key))
                    if s is None:
                        s = hub.attach(await asyncio.to_thread(hub.prepare, root, spec, keys))
                    await asyncio.to_thread(hub.ensure_prime, s, keys)   # sessions the new studies read (noise band ...)
                    # an smt study reads the partner market (NQ against ES): its stream is built beside this one
                    hub.link_peer(s, await asyncio.to_thread(hub.prepare_peer, root, spec, keys))
                    if not s.subs:
                        s.retain(keys)      # the studies this chart no longer asks for stop running
                    for k in keys:
                        s.add_study(k)
                    hub.subscribe(s, (conn, cid), bool(msg.get("flow", True)))
                    # fp / big: a chart that draws no footprint / no big prints asks for its bars without
                    # them (cell.js need()); a sub that says nothing gets both, as before
                    conn.send({"type": "history", "id": cid,
                               **s.payload(bool(msg.get("fp", True)), bool(msg.get("big", True)),
                                           bool(msg.get("flow", True)))})
                    if depth is not None:
                        depth.view((conn, cid), root, conn.send, room)   # after `history`: depth follows it
                        booklive.view((conn, cid), root, conn.send, room)   # and the book flow's recent state
                except Exception as e:  # noqa: BLE001 — an unexpected failure building the
                                        # stream must not drop every chart on the page either
                    log(f"sub {cid} ({root} {spec.key}): {type(e).__name__}: {e}\n{traceback.format_exc()}")
                    conn.send({"type": "error", "id": cid, "error": str(e)})
                    # never leave this id subscribed to a stream it only got an
                    # error for (the pump would keep sending it `update`s for
                    # an id that never got `history`), and never leave a
                    # freshly attached, now-subscriberless stream in hub.streams
                    hub.unsubscribe((conn, cid))
                    if depth is not None:
                        depth.unview((conn, cid))
                        booklive.unview((conn, cid))
                    if s is not None and not s.subs and hub.streams.get(s.key) is s:
                        del hub.streams[s.key]
                    continue
        except (WebSocketDisconnect, RuntimeError):
            # RuntimeError: starlette raises this on the receive loop if Conn's
            # writer already closed the socket out from under us (SEND_QUEUE_MAX
            # overflow) -- same clean-up as an ordinary client disconnect.
            pass
        finally:
            conns.discard(conn)
            desk_fan.detach(conn)
            if depth is not None:
                depth.drop_conn(conn)
                booklive.drop_conn(conn)
            tapelive.drop_conn(conn)
            hub.drop_conn(conn)
            replays.drop_conn(conn)
            conn.task.cancel()
