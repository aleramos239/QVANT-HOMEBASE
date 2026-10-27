"""The md/order socket logs HOW it ended (close code, reason, who closed first), with a clock time.
A local websockets server stands in for Tradovate: nothing leaves this machine."""
from __future__ import annotations

import asyncio

import websockets

from homebase.broker.tradovate_ws import TradovateWS

_real_connect = websockets.connect   # conftest swaps websockets.connect for a refusal; this is the real one, used on localhost only


async def _ended(handler, capsys) -> str:
    async with websockets.serve(handler, "127.0.0.1", 0) as srv:
        t = TradovateWS("tok")
        t.url = f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}"
        t.ws = await _real_connect(t.url)
        await t._reader()
    return capsys.readouterr().err


def test_a_server_close_with_a_code_is_logged_with_code_reason_and_peer(capsys):
    async def h(ws):
        await ws.close(4001, "kicked")
    err = asyncio.run(_ended(h, capsys))
    assert "websocket ended clean" not in err or "code=4001" in err
    assert "code=4001" in err and "reason='kicked'" in err and "first=peer" in err


def test_a_normal_close_is_logged_too_it_used_to_be_silent(capsys):
    async def h(ws):
        await ws.close()
    err = asyncio.run(_ended(h, capsys))
    assert "websocket ended clean: code=1000" in err and "first=peer" in err


def test_a_cut_connection_is_logged_with_no_close_frame(capsys):
    async def h(ws):
        ws.transport.abort()
        await asyncio.sleep(0.1)
    err = asyncio.run(_ended(h, capsys))
    assert "websocket closed: code=1006" in err and "first=none" in err
