"""The T4 protobuf codec: golden bytes, a sell's 10-byte varint, a bracket, unknown fields, truncation."""
import struct

import pytest

from homebase.broker.alphatrader_proto import (
    AUTO_OCO_P, BUY, GTC, HOLD, LIMIT, SELL, STOP_MARKET,
    client, decode, encode, price, price_of, server,
)


def _varint(n):
    out = bytearray()
    while n > 0x7F:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    return bytes(out + bytes([n]))


def test_heartbeat_golden_bytes():
    assert client("heartbeat", {"timestamp": 1}) == bytes.fromhex("0a020801")


def test_account_subscribe_golden_bytes():
    data = {"subscribe": 2, "subscribeAllAccounts": True, "uplMode": 1}
    assert client("accountSubscribe", data) == bytes.fromhex("c20c06080210012001")


def test_order_submit_tag_is_2402():
    assert client("orderSubmit", {"accountId": "A"})[:2] == bytes.fromhex("e212")


def test_sell_is_a_ten_byte_varint_and_decodes_to_minus_one():
    raw = encode("OrderSubmit.Order", {"buySell": -1})
    assert raw == bytes.fromhex("08ffffffffffffffffff01")
    assert decode("OrderSubmit.Order", raw) == {"buySell": -1}


def test_bracket_round_trip():
    bracket = {
        "accountId": "acc-1", "marketId": "mkt-NQ", "orderLink": AUTO_OCO_P,
        "orders": [
            {"buySell": BUY, "priceType": LIMIT, "volume": 2, "limitPrice": price(20000.13, .25),
             "tag": "e", "ClOrdId": "c1"},
            {"buySell": SELL, "priceType": LIMIT, "timeType": GTC, "limitPrice": price(20010, .25),
             "tag": "t", "activationType": HOLD, "ClOrdId": "c2"},
            {"buySell": SELL, "priceType": STOP_MARKET, "timeType": GTC, "stopPrice": price(19990, .25),
             "tag": "s", "activationType": HOLD, "ClOrdId": "c3"},
        ],
    }
    assert decode("OrderSubmit", encode("OrderSubmit", bracket)) == bracket


def test_server_message_payload_and_unknown_fields_skipped():
    trade = {"uniqueId": "u1", "accountId": "A", "totalFillVolume": 2, "price": price(20000.25, .25)}
    body = encode("OrderUpdateTrade", trade)
    unknown = (_varint(999 << 3 | 0) + _varint(7)
               + _varint(999 << 3 | 1) + b"\x00" * 8
               + _varint(999 << 3 | 2) + _varint(3) + b"abc"
               + _varint(999 << 3 | 5) + b"\x00" * 4)
    buf = unknown + _varint(304 << 3 | 2) + _varint(len(body)) + body + unknown
    assert server(buf) == ("orderUpdateTrade", trade)
    assert server(b"") == ("", {})
    assert server(unknown) == ("", {})


def test_double_and_int64_round_trip():
    raw = encode("AccountUpdate", {"balance": 50123.45})
    assert raw[1:] == struct.pack("<d", 50123.45)
    assert decode("AccountUpdate", raw) == {"balance": 50123.45}
    assert decode("Heartbeat", encode("Heartbeat", {"timestamp": 1761868800000})) == {"timestamp": 1761868800000}


def test_truncated_buffer_raises_ValueError():
    good = client("heartbeat", {"timestamp": 1761868800000})
    for cut in range(1, len(good)):
        with pytest.raises(ValueError):
            server(good[:cut])
    with pytest.raises(ValueError):
        decode("AccountUpdate", b"\x19\x00\x00")  # double cut short


def test_price_rounds_to_tick():
    assert price(20000.13, .25) == {"value": "20000.25"}
    assert price(2400.04, .1) == {"value": "2400.0"}
    assert price_of({"value": "20000.25"}) == 20000.25
    assert price_of(None) is None
