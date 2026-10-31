"""A small T4 protobuf codec for the AlphaTrader (Alpha Futures) connection. Standard library only.

Field numbers and enum values are read from the AlphaTrader site bundle (`t4proto.v1`); only the messages
the connection uses are here. One ClientMessage / ServerMessage per websocket frame, no length prefix.
"""
import struct
from decimal import ROUND_HALF_UP, Decimal

# --- enums (t4proto.v1) ---
BUY, SELL = 1, -1                                                    # BuySell; SELL goes out as a 10-byte varint
MARKET, LIMIT, STOP_MARKET, STOP_LIMIT = 0, 1, 2, 3                  # PriceType
NORMAL, GTC = 0, 2                                                   # TimeType
WORKING, FINISHED, REJECTED, HELD = 1, 2, 3, 4                       # OrderStatus (NONE 0)
AUTO_OCO_P = 7                                                       # OrderLink (NONE 0)
IMMEDIATE, HOLD = 0, 1                                               # ActivationType
LOGIN_OK, LOGIN_FAILED, LOGGED_IN_ELSEWHERE, LOGOUT = 0, 1, 6, 7     # LoginResult
UNAUTHORIZED, LOCKED_OUT, TWO_FACTOR_REQUIRED = 9, 18, 24            # LoginResult
ALL_UPDATES = 2                                                      # AccountSubscribeType
AVERAGE = 1                                                          # UPLMode


def _f(name, kind, sub=None, rep=False):
    return (name, kind, sub, rep)


_S, _B, _I32, _I64, _D = (_f("", k) for k in ("string", "bool", "int32", "int64", "double"))


def _m(**fields):
    """`name=(number, spec)` -> {number: (name, kind, sub_message, repeated)}."""
    return {num: (name, *spec[1:]) for name, (num, spec) in fields.items()}


def _msg(sub, rep=False):
    return _f("", "msg", sub, rep)


SCHEMAS = {
    # t4proto.v1.service.ClientMessage
    "ClientMessage": _m(
        heartbeat=(1, _msg("Heartbeat")), loginRequest=(2, _msg("LoginRequest")),
        accountSubscribe=(200, _msg("AccountSubscribe")), orderSubmit=(300, _msg("OrderSubmit")),
        orderPull=(302, _msg("OrderPull"))),
    # t4proto.v1.service.ServerMessage
    "ServerMessage": _m(
        heartbeat=(1, _msg("Heartbeat")), loginResponse=(2, _msg("LoginResponse")),
        accountSubscribeResponse=(200, _msg("AccountSubscribeResponse")),
        accountPosition=(202, _msg("AccountPosition")), accountUpdate=(203, _msg("AccountUpdate")),
        accountDetails=(204, _msg("AccountDetails")), accountSnapshot=(205, _msg("AccountSnapshot")),
        accountProfit=(206, _msg("AccountProfit")), orderUpdate=(300, _msg("OrderUpdate")),
        orderUpdateMulti=(301, _msg("OrderUpdateMulti")), orderUpdateFailed=(302, _msg("OrderUpdateFailed")),
        orderUpdateStatus=(303, _msg("OrderUpdateStatus")), orderUpdateTrade=(304, _msg("OrderUpdateTrade"))),
    # t4proto.v1.service.Heartbeat
    "Heartbeat": _m(timestamp=(1, _I64)),
    # t4proto.v1.auth.LoginRequest
    "LoginRequest": _m(firm=(2, _S), username=(3, _S), password=(4, _S), appName=(5, _S), appLicense=(6, _S),
                       priceFormat=(10, _I32)),
    # t4proto.v1.auth.LoginResponse
    "LoginResponse": _m(result=(1, _I32), sessionId=(2, _S), userId=(3, _S), errorMessage=(6, _S),
                        accounts=(8, _msg("LoginResponse.Account", True))),
    # t4proto.v1.auth.LoginResponse.Account
    "LoginResponse.Account": _m(accountId=(1, _S), accountNumber=(2, _S), accountName=(3, _S),
                                displayName=(4, _S), mode=(5, _I32)),
    # t4proto.v1.account.AccountSubscribe
    "AccountSubscribe": _m(subscribe=(1, _I32), subscribeAllAccounts=(2, _B), accountId=(3, _S), uplMode=(4, _I32)),
    # t4proto.v1.account.AccountSubscribeResponse
    "AccountSubscribeResponse": _m(success=(1, _B), errors=(2, _S)),
    # t4proto.v1.account.AccountPosition
    "AccountPosition": _m(accountId=(1, _S), contractId=(3, _S), marketId=(4, _S), buys=(5, _I32), sells=(6, _I32),
                          workingBuys=(7, _I32), workingSells=(8, _I32), rpl=(9, _D),
                          averageOpenPrice=(27, _msg("Price"))),
    # t4proto.v1.account.AccountUpdate
    "AccountUpdate": _m(accountId=(1, _S), status=(2, _I32), balance=(3, _D), rpl=(4, _D)),
    # t4proto.v1.account.AccountDetails
    "AccountDetails": _m(accountId=(1, _S), accountName=(2, _S), account=(3, _S), enabled=(4, _B), mode=(23, _I32),
                         displayName=(26, _S), groupName=(34, _S)),
    # t4proto.v1.account.AccountProfit
    "AccountProfit": _m(accountId=(1, _S), upl=(3, _D), rpl=(5, _D)),
    # t4proto.v1.account.AccountSnapshot
    "AccountSnapshot": _m(accountId=(1, _S), messages=(6, _msg("AccountSnapshotMessage", True))),
    # t4proto.v1.account.AccountSnapshot.AccountSnapshotMessage
    "AccountSnapshotMessage": _m(accountPosition=(3, _msg("AccountPosition")), accountUpdate=(4, _msg("AccountUpdate")),
                                 accountDetails=(5, _msg("AccountDetails")),
                                 orderUpdateMulti=(8, _msg("OrderUpdateMulti"))),
    # t4proto.v1.orderrouting.OrderSubmit
    "OrderSubmit": _m(accountId=(2, _S), marketId=(3, _S), orderLink=(4, _I32), manualOrderIndicator=(5, _B),
                      orders=(6, _msg("OrderSubmit.Order", True))),
    # t4proto.v1.orderrouting.OrderSubmit.Order
    "OrderSubmit.Order": _m(buySell=(1, _I32), priceType=(2, _I32), timeType=(3, _I32), volume=(4, _I32),
                            limitPrice=(7, _msg("Price")), stopPrice=(8, _msg("Price")), tag=(10, _S),
                            activationType=(11, _I32), ClOrdId=(13, _S)),
    # t4proto.v1.orderrouting.OrderPull
    "OrderPull": _m(accountId=(2, _S), marketId=(3, _S), manualOrderIndicator=(4, _B),
                    pulls=(5, _msg("OrderPull.Pull", True))),
    # t4proto.v1.orderrouting.OrderPull.Pull
    "OrderPull.Pull": _m(uniqueId=(1, _S), tag=(2, _S), ClOrdId=(3, _S)),
    # t4proto.v1.orderrouting.OrderUpdate
    "OrderUpdate": _m(uniqueId=(1, _S), accountId=(2, _S), marketId=(3, _S), change=(6, _I32), status=(7, _I32),
                      statusDetail=(8, _S), buySell=(23, _I32), priceType=(24, _I32), currentVolume=(26, _I32),
                      currentLimitPrice=(27, _msg("Price")), currentStopPrice=(28, _msg("Price")), tag=(47, _S),
                      totalFillVolume=(48, _I32), workingVolume=(49, _I32), orderLink=(54, _I32),
                      ordersLinked=(55, _I32), activationType=(56, _I32), tagClOrdId=(66, _S),
                      trades=(77, _msg("OrderUpdate.Trade", True))),
    # t4proto.v1.orderrouting.OrderUpdate.Trade
    "OrderUpdate.Trade": _m(sequenceOrder=(1, _I32), volume=(2, _I32), price=(3, _msg("Price")),
                            exchangeTradeId=(6, _S), tradeDate=(10, _I64)),
    # t4proto.v1.orderrouting.OrderUpdateMulti
    "OrderUpdateMulti": _m(marketId=(1, _S), accountId=(2, _S), historical=(3, _B),
                           updates=(4, _msg("OrderUpdateMulti.Update", True))),
    # t4proto.v1.orderrouting.OrderUpdateMulti.Update
    "OrderUpdateMulti.Update": _m(orderUpdate=(3, _msg("OrderUpdate")), orderUpdateFailed=(4, _msg("OrderUpdateFailed")),
                                  orderUpdateStatus=(5, _msg("OrderUpdateStatus")),
                                  orderUpdateTrade=(6, _msg("OrderUpdateTrade"))),
    # t4proto.v1.orderrouting.OrderUpdateStatus
    "OrderUpdateStatus": _m(uniqueId=(1, _S), accountId=(2, _S), marketId=(3, _S), change=(6, _I32), status=(7, _I32),
                            statusDetail=(8, _S), currentVolume=(11, _I32), currentLimitPrice=(12, _msg("Price")),
                            currentStopPrice=(13, _msg("Price")), priceType=(14, _I32), workingVolume=(16, _I32),
                            tag=(33, _S), tagClOrdId=(34, _S)),
    # t4proto.v1.orderrouting.OrderUpdateTrade
    "OrderUpdateTrade": _m(uniqueId=(1, _S), accountId=(2, _S), marketId=(3, _S), change=(6, _I32), status=(7, _I32),
                           totalFillVolume=(10, _I32), workingVolume=(11, _I32), volume=(12, _I32),
                           price=(13, _msg("Price")), exchangeTradeId=(15, _S), tradeDate=(18, _I64),
                           sequenceOrder=(19, _I32)),
    # t4proto.v1.orderrouting.OrderUpdateFailed
    "OrderUpdateFailed": _m(uniqueId=(1, _S), accountId=(2, _S), marketId=(3, _S), change=(6, _I32), status=(7, _I32),
                            statusDetail=(8, _S), tagClOrdId=(10, _S)),
    # t4proto.v1.common.Price
    "Price": _m(value=(1, _S)),
}

# wire type per kind: 0 varint, 1 fixed64, 2 length-delimited
_WIRE = {"string": 2, "msg": 2, "double": 1, "bool": 0, "int32": 0, "int64": 0}


def _varint(n):
    n &= 0xFFFFFFFFFFFFFFFF  # a negative number is sign-extended to 64 bits (10 bytes)
    out = bytearray()
    while n > 0x7F:
        out.append(n & 0x7F | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def encode(msg, data):
    out = bytearray()
    for num, (name, kind, sub, rep) in sorted(SCHEMAS[msg].items()):
        value = data.get(name)
        for v in (value or []) if rep else [value]:
            if v is None or (kind != "msg" and not v):  # proto3 defaults are left out
                continue
            out += _varint(num << 3 | _WIRE[kind])
            if kind == "string":
                b = v.encode()
                out += _varint(len(b)) + b
            elif kind == "msg":
                b = encode(sub, v)
                out += _varint(len(b)) + b
            elif kind == "double":
                out += struct.pack("<d", v)
            else:
                out += _varint(int(v))
    return bytes(out)


def _read_varint(buf, i):
    n = shift = 0
    while True:
        if i >= len(buf) or shift > 63:
            raise ValueError("truncated or over-long varint")
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if b < 0x80:
            return n, i
        shift += 7


def decode(msg, buf):
    schema, out, i = SCHEMAS[msg], {}, 0
    while i < len(buf):
        tag, i = _read_varint(buf, i)
        num, wt = tag >> 3, tag & 7
        if wt == 0:
            raw, i = _read_varint(buf, i)
        elif wt == 1 or wt == 5:
            end = i + (8 if wt == 1 else 4)
            if end > len(buf):
                raise ValueError("truncated fixed-width field")
            raw, i = buf[i:end], end
        elif wt == 2:
            n, i = _read_varint(buf, i)
            if i + n > len(buf):
                raise ValueError("truncated length-delimited field")
            raw, i = buf[i:i + n], i + n
        else:
            raise ValueError(f"unsupported wire type {wt}")
        spec = schema.get(num)
        if spec is None or _WIRE[spec[1]] != wt:  # unknown field, or not the type we know: skip it
            continue
        name, kind, sub, rep = spec
        if kind == "string":
            v = raw.decode()
        elif kind == "msg":
            v = decode(sub, raw)
        elif kind == "double":
            if len(raw) != 8:
                raise ValueError("bad double")
            v = struct.unpack("<d", raw)[0]
        elif kind == "bool":
            v = raw != 0
        elif kind == "int32":
            v = raw & 0xFFFFFFFF
            v -= (v >= 1 << 31) << 32
        else:
            v = raw - ((raw >= 1 << 63) << 64)
        if rep:
            out.setdefault(name, []).append(v)
        else:
            out[name] = v
    return out


def client(payload, data):
    return encode("ClientMessage", {payload: data})


def server(buf):
    """The payload name set in a ServerMessage and its dict; ("", {}) when empty or unknown."""
    for name, data in decode("ServerMessage", buf).items():
        return name, data
    return "", {}


def price(x, tick):
    """A common.Price rounded to the tick, written with the tick's decimals."""
    t = Decimal(repr(tick))
    n = (Decimal(repr(x)) / t).to_integral_value(ROUND_HALF_UP)
    return {"value": f"{n * t:.{max(0, -t.as_tuple().exponent)}f}"}


def price_of(p):
    return float(p["value"]) if p and p.get("value") else None
