# AlphaTrader Broker Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An Alpha Futures account (platform AlphaTrader) can be added from the desk wizard with the owner's Alpha email +
password and sits on the desk like a TopstepX account, with booking refused until the owner lifts it.

**Architecture:** One `AtrSession` per Alpha login. It holds the Alpha tokens, renews them, and fetches the T4 login from
Alpha's credentials JWT, going through the login budget. One `AtrSocket` per login carries CTS T4 protobuf over a binary
websocket and is shared by every desk entry on that login (the TopstepX pattern: `brokers._ATR_SESSIONS`). `AlphaTraderAdapter`
(one per desk entry) sends orders on that socket and reads fills, positions and orders from it. A hand-written codec
(`alphatrader_proto.py`) encodes and decodes the few T4 messages needed.

**Tech Stack:** Python 3, `httpx` (Alpha REST), `websockets` (binary frames), FastAPI routes, plain JS in `homebase/static`.

**Spec:** `docs/superpowers/specs/2026-10-30-alphatrader-broker-design.md` (approved by the owner 2026-10-30).
**Model code (read it, copy its shape, do not import or change it):** `homebase/broker/topstepx*.py`, `tests/test_topstepx_*.py`,
and the TopstepX branches in `homebase/desk_app/brokers.py`, `homebase/routes/accounts.py`, `homebase/routes/strategies.py`,
`homebase/static/desk/book.js`, `homebase/static/index.html`.

## Global Constraints

- Work only on `feat/alphatrader` in `.worktrees/alphatrader`. Never merge to `main`; main ships to the live VPS by itself. Merge only when the owner says so.
- No new dependency (`protobuf` is NOT installed; never add it). `httpx` and `websockets` are already there.
- Login key: `atr:<email lowercased>`. `secrets_store.set_credentials(key, username=<email>, password=...)`. Tokens and the decoded T4 credentials live in memory only.
- The password, the Alpha tokens, the `signed_credential_token` and the decoded T4 password never reach a log line, the journal, an exception message, an HTTP answer, `repr()` or git.
- The login budget (`homebase/broker/login_budget.py`) books every Alpha password login and every T4 socket login. An Alpha token refresh and a credential-token fetch are free.
- One `asyncio.Lock` per session covers Alpha login, refresh, credential fetch and T4 login. Renewal, the kick handler and the wizard all take it.
- A bracket is ONE `OrderSubmit` (entry + target + stop, `orderLink` AUTO_OCO_P), never a later separate order.
- `ATR_BOOKING_OPEN = False` and `ATR_FLATTEN_IF_NO_STOP = False` in `alphatrader.py`.
- Unknown is never flat: `get_net_position` raises (never returns 0) while the position cache is unseeded or dirty.
- Tests never reach the network. Add `"test_alphatrader"` to the guard tuple in `tests/conftest.py:125`.
- Do not change TopstepX, Tradovate or Vest behaviour. Do not touch `deploy/`.
- Shell hooks block commands that contain order-placing words, and block `rm -rf`. Read broker files with the Read tool, and move unwanted files to `~/.Trash`.
- Every unconfirmed value is a named constant at the top of its module with the comment `# unconfirmed`, so the spike's corrections touch one place.

## Facts (read from the site bundle, 2026-10-30)

The saved bundle is `.spike/alphatrader-main.2fcc5e96.js`. The field and enum dumps are `.spike/t4_fields.txt` and
`.spike/t4_enums.txt`. All three are git-excluded, so read them, never commit them.

| What | Value |
|---|---|
| Alpha REST base | `https://apiv2.alphatrader.com` |
| Alpha login | `POST /api/v1/auth/login/` JSON `{"email", "password"}` (field names unconfirmed) → `data.tokens` {`access_token`?, `refresh_token`, `id_token`} (`data.tokens` or `data`; names unconfirmed) |
| Refresh / profile | `POST /api/v1/auth/token/refresh/ {"refresh_token"}`; `GET /api/v1/auth/me/` (Bearer) |
| T4 login | `POST /api/v1/t4/credentials/token/` (Bearer) → `data.signed_credential_token`, a JWT; payload `t4_firm`, `t4_username`, `t4_password`, `t4_app_name`, `t4_app_license` |
| Symbols | `GET /api/v1/market/symbols/?page_size=100&search=<root>`: rows that give the T4 `marketId` (row shape: spike) |
| Exchanges | NQ, MNQ, ES, MES → `CME_Eq`; GC, MGC → `CME_CO` |
| T4 socket | `wss://wss-sim.t4login.com/v1`, binary frames, one `ClientMessage` / `ServerMessage` per frame, no length prefix |
| Heartbeat | send `heartbeat {timestamp: ms}` every 20 s; close and reconnect after 60 s with nothing received |
| After connect | send `loginRequest {firm, username, password, appName, appLicense, priceFormat: 0}`; on `loginResponse.result == 0`, send `accountSubscribe {subscribe: 2, subscribeAllAccounts: true, uplMode: 1}` |
| Bracket | `orderSubmit {accountId, marketId, orderLink: 7 (AUTO_OCO_P), manualOrderIndicator: false, orders: [entry, target, stop]}`. Target = opposite side, LIMIT, GTC, `volume 0`, `limitPrice`, `activationType 1` (HOLD). Stop = opposite side, STOP_MARKET, GTC, `volume 0`, `stopPrice`, `activationType 1`. Every order has a `tag` and a unique `ClOrdId` |
| Prices | `common.Price {value: "<decimal string>"}`, rounded to the tick |

**Field numbers** (`ClientMessage` / `ServerMessage` payload numbers, then each message's fields; full lists in `.spike/t4_fields.txt`):

- ClientMessage: heartbeat 1, loginRequest 2, accountSubscribe 200, orderSubmit 300, orderRevise 301, orderPull 302.
- ServerMessage: heartbeat 1, loginResponse 2, accountSubscribeResponse 200, accountPosition 202, accountUpdate 203,
  accountDetails 204, accountSnapshot 205, accountProfit 206, orderUpdate 300, orderUpdateMulti 301, orderUpdateFailed 302,
  orderUpdateStatus 303, orderUpdateTrade 304.
- Heartbeat: timestamp 1 (int64).
- LoginRequest: firm 2, username 3, password 4, appName 5, appLicense 6, priceFormat 10 (int32).
- LoginResponse: result 1, sessionId 2, userId 3, errorMessage 6, accounts 8 (repeated Account: accountId 1, accountNumber 2,
  accountName 3, displayName 4, mode 5).
- AccountSubscribe: subscribe 1, subscribeAllAccounts 2 (bool), accountId 3, uplMode 4.
- AccountSubscribeResponse: success 1, errors 2.
- AccountPosition: accountId 1, contractId 3, marketId 4, buys 5, sells 6, workingBuys 7, workingSells 8, rpl 9 (double),
  averageOpenPrice 27 (Price).
- AccountUpdate: accountId 1, status 2, balance 3 (double), rpl 4 (double).
- AccountDetails: accountId 1, accountName 2, account 3, enabled 4, mode 23, displayName 26, groupName 34.
- AccountProfit: accountId 1, upl 3, rpl 5 (doubles).
- AccountSnapshot: accountId 1, messages 6 (repeated AccountSnapshotMessage: accountPosition 3, accountUpdate 4,
  accountDetails 5, orderUpdateMulti 8).
- OrderSubmit: accountId 2, marketId 3, orderLink 4, manualOrderIndicator 5 (bool), orders 6 (repeated Order).
- OrderSubmit.Order: buySell 1, priceType 2, timeType 3, volume 4, limitPrice 7, stopPrice 8, tag 10, activationType 11, ClOrdId 13.
- OrderPull: accountId 2, marketId 3, manualOrderIndicator 4, pulls 5 (repeated Pull: uniqueId 1, tag 2, ClOrdId 3).
- OrderUpdate: uniqueId 1, accountId 2, marketId 3, change 6, status 7, statusDetail 8, buySell 23, priceType 24,
  currentVolume 26, currentLimitPrice 27, currentStopPrice 28, tag 47, totalFillVolume 48, workingVolume 49, orderLink 54,
  ordersLinked 55, activationType 56, tagClOrdId 66, trades 77 (repeated Trade: sequenceOrder 1, volume 2, price 3,
  exchangeTradeId 6, tradeDate 10).
- OrderUpdateMulti: marketId 1, accountId 2, historical 3, updates 4 (repeated: orderUpdate 3, orderUpdateFailed 4,
  orderUpdateStatus 5, orderUpdateTrade 6).
- OrderUpdateStatus: uniqueId 1, accountId 2, marketId 3, change 6, status 7, statusDetail 8, currentVolume 11,
  currentLimitPrice 12, currentStopPrice 13, priceType 14, workingVolume 16, tag 33, tagClOrdId 34.
- OrderUpdateTrade: uniqueId 1, accountId 2, marketId 3, change 6, status 7, totalFillVolume 10, workingVolume 11, volume 12,
  price 13, exchangeTradeId 15, tradeDate 18, sequenceOrder 19.
- OrderUpdateFailed: uniqueId 1, accountId 2, marketId 3, change 6, status 7, statusDetail 8, tagClOrdId 10.
- Price: value 1 (string).

**Enums:**
- BuySell: BUY 1, SELL −1 (encoded as a 10-byte varint).
- PriceType: MARKET 0, LIMIT 1, STOP_MARKET 2, STOP_LIMIT 3.
- TimeType: NORMAL 0, GTC 2.
- OrderStatus: NONE 0, WORKING 1, FINISHED 2, REJECTED 3, HELD 4.
- OrderLink: NONE 0, AUTO_OCO_P 7.
- ActivationType: IMMEDIATE 0, HOLD 1.
- LoginResult: SUCCESS 0, FAILED 1, LOGGED_IN_ELSEWHERE 6, LOGOUT 7, UNAUTHORIZED 9, LOCKED_OUT 18, TWO_FACTOR_REQUIRED 24.
- AccountSubscribeType: ALL_UPDATES 2. UPLMode: AVERAGE 1.

Wire types: string, bytes and messages are 2; int32, int64, bool and enum are 0 (varint; a negative int32 is sign-extended
to 64 bits, 10 bytes); double is 1 (8 bytes, little-endian).

## Review Focus

1. **A sell order: `buySell = -1`.** A wrong varint (5 bytes, or unsigned) makes T4 refuse it or read it as a buy. Expect the 10-byte encoding, and a decode back to −1. (Task 1 test.)
2. **The owner opens AlphaTrader in a browser while a position is open.** Expect: `loginResponse.result == 6` (or the socket drops), `atr_session_taken` journaled, ONE new credential fetch + T4 login through the budget, the socket back, and missed fills replayed once from the account snapshot. (Task 6 test.)
3. **An order with no answer within the wait.** Expect `OrderResult(ok=False, raw={"outcome_unknown": True})`, never a resend. A late `orderUpdate` with that `ClOrdId` still lands in the order cache. (Task 5 test.)
4. **A position update for a market Homebase never resolved (an older month after a roll, or one opened by hand).** Expect it counted in the root's net and closed by flatten. Never ignored, never treated as flat. (Task 6 test.)
5. **An Alpha refresh token that has expired or been revoked.** Expect one password login through the budget, not a loop. A code request stops with "AlphaTrader needs a code". (Task 2 test.)

---

### Task 0: Read-only spike script (written now, run by the owner once he owns an account)

**Files:**
- Create (not committed, `.spike/` is excluded): `.spike/atr_spike.py`

The build does not wait for the spike. It only gates booking and the first order (Task 9).

- [ ] **Step 1: Write the spike.** It asks for the email with `input()` and the password with `getpass.getpass()`, saves nothing, and sends no order, pull or revise. Read-only steps:
  - `POST /api/v1/auth/login/`: print the status, the answer's KEYS at every level, and any message or code-step words, never a token. If no tokens come back, print the keys and stop.
  - `GET /api/v1/auth/me/`: print the keys.
  - `POST /api/v1/t4/credentials/token/`: print the decoded JWT payload's KEYS, plus `t4_firm` and `t4_app_name` (both safe), and the `exp` lifetime in minutes. Never print `t4_password`, `t4_username` or `t4_app_license`.
  - `GET /api/v1/t4/accounts/` and `GET /api/v1/market/symbols/?search=NQ`: print the keys and up to 3 rows with only id, name, market, contract, exchange and expiry fields.
  - The T4 socket: login, then print `loginResponse.result`, `errorMessage` and each account's id, name, displayName and mode. Then `accountSubscribe`, and for 60 s print each ServerMessage payload name and its decoded field names. Tell the owner to log in on the site after about 20 s, to show what a kick looks like.
  - The spike imports the codec from Task 1, so write it after Task 1. Its own dict printing must use a SAFE key list, as `.worktrees/topstepx/.spike/tsx_spike.py` does.
- [ ] **Step 2:** Do not run it. The owner runs it later: `cd /Users/ramoscapital/ramos-quant-homebase/.worktrees/alphatrader && /Users/ramoscapital/ramos-quant-homebase/.venv/bin/python .spike/atr_spike.py`.

### Task 1: The T4 protobuf codec

**Files:**
- Create: `homebase/broker/alphatrader_proto.py`
- Test: `tests/test_alphatrader_proto.py`

**Interfaces:**
- Produces:
  - `SCHEMAS: dict[str, dict[int, tuple[str, str, str | None, bool]]]`: message name → field number → `(name, kind, sub_message_or_None, repeated)`. Kinds are `"string" | "bool" | "int32" | "int64" | "double" | "msg"`. It covers every message listed in the Facts.
  - `encode(msg: str, data: dict) -> bytes`. Leave out None, `""`, 0 and False (proto3 defaults). Repeated message fields are lists of dicts.
  - `decode(msg: str, buf: bytes) -> dict`. Skip unknown fields of every wire type (0, 1, 2, 5). Repeated fields come back as lists. Raise `ValueError` on a truncated buffer.
  - `client(payload: str, data: dict) -> bytes`, shorthand for `encode("ClientMessage", {payload: data})`.
  - `server(buf: bytes) -> tuple[str, dict]`: the one payload name set in a `ServerMessage`, and its dict. An empty or unknown payload gives `("", {})`.
  - `price(x: float, tick: float) -> dict` → `{"value": "<x rounded to tick, no trailing zeros beyond the tick's decimals>"}`; `price_of(p: dict | None) -> float | None`.
  - Enum constants named as in the Facts, e.g. `BUY = 1`, `SELL = -1`, `LIMIT = 1`, `STOP_MARKET = 2`, `AUTO_OCO_P = 7`, `HOLD = 1`, `GTC = 2`, `WORKING = 1`, `FINISHED = 2`, `REJECTED = 3`, `HELD = 4`, `LOGIN_OK = 0`, `LOGGED_IN_ELSEWHERE = 6`, `TWO_FACTOR_REQUIRED = 24`.
  - Each schema block gets a one-line comment naming its message in `t4proto.v1`, for example `# t4proto.v1.orderrouting.OrderSubmit`.

- [ ] **Step 1: Write the failing tests:**
  - `test_heartbeat_golden_bytes`: `client("heartbeat", {"timestamp": 1}) == bytes.fromhex("0a020801")`.
  - `test_account_subscribe_golden_bytes`: `client("accountSubscribe", {"subscribe": 2, "subscribeAllAccounts": True, "uplMode": 1}) == bytes.fromhex("c20c06080210012001")`.
  - `test_order_submit_tag_is_2402`: `client("orderSubmit", {"accountId": "A"})[:2] == bytes.fromhex("e212")`.
  - `test_sell_is_a_ten_byte_varint_and_decodes_to_minus_one`: `encode("OrderSubmit.Order", {"buySell": -1}) == bytes.fromhex("08ffffffffffffffffff01")` and decoding gives `{"buySell": -1}`. (Review Focus 1)
  - `test_bracket_round_trip`: a three-order `OrderSubmit` (the Facts' bracket, prices as `price()`) encodes and decodes back to the same dict.
  - `test_server_message_payload_and_unknown_fields_skipped`: a `ServerMessage` holding `orderUpdateTrade`, plus an unknown field 999 of each wire type, gives `("orderUpdateTrade", {...})` with the known fields only.
  - `test_double_and_int64_round_trip`: `AccountUpdate.balance = 50123.45`, `Heartbeat.timestamp = 1761868800000`.
  - `test_truncated_buffer_raises_ValueError`.
  - `test_price_rounds_to_tick`: `price(20000.13, .25) == {"value": "20000.25"}`, `price(2400.04, .1) == {"value": "2400.0"}`, `price_of({"value": "20000.25"}) == 20000.25`.
- [ ] **Step 2: Run** `pytest tests/test_alphatrader_proto.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement `alphatrader_proto.py`.** Use the standard library only (`struct` for doubles).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "alphatrader: a small T4 protobuf codec (field numbers from the AlphaTrader bundle)"`.

### Task 2: The login session (`AtrSession`)

**Files:**
- Create: `homebase/broker/alphatrader_auth.py`
- Modify: `tests/conftest.py:125`: add `"test_alphatrader"` to the tuple.
- Test: `tests/test_alphatrader_auth.py`

**Interfaces:**
- Consumes: `LoginBudget`, `LoginDeferred` (`homebase/broker/login_budget.py`), `secrets_store`, `tradovate_auth.USER_AGENT`.
- Produces:
  - Constants: `BASE = "https://apiv2.alphatrader.com"`, `WS_URL = "wss://wss-sim.t4login.com/v1"`,
    `HEADERS` (Origin and Referer `https://futures.alphatrader.com`, browser UA), `RENEW_LEFT_S = 600`,
    `LOGIN_PATH`, `REFRESH_PATH`, `ME_PATH`, `CRED_PATH`, `LOGIN_FIELDS = ("email", "password")`,
    and the token field names, each marked `# unconfirmed`.
  - `class NeedsCode(RuntimeError)`, `class AtrLoginFailed(RuntimeError)` (Alpha's words, never the password).
  - `@dataclass(repr=False) class T4Creds: firm, username, password, app_name, app_license`. Its `__repr__` shows only `firm` and `app_name`.
  - `class AtrSession(key: str, *, http: httpx.AsyncClient | None = None, budget: LoginBudget | None = None)`:
    - `lock: asyncio.Lock`, `budget`, `journal: Callable | None`, `taken: int`, `lost: str | None` (why the session is down, shown on the card).
    - `async login(code: str | None = None) -> None`: one password login. It is booked on the budget (`blocked` → raise `LoginDeferred`, else `record_login` … `login_result`), and keeps the access, refresh and id tokens and the access expiry (JWT `exp`).
    - `async access() -> str`: renews with the refresh token when under `RENEW_LEFT_S` left. If that fails, it does a password `login()` through the budget. Free when it does not log in.
    - `async request(method: str, path: str, **kw) -> httpx.Response`: adds the Bearer. On a 401, one renewal then one retry.
    - `async t4_creds() -> T4Creds`: `POST CRED_PATH`, then decodes the JWT payload with base64 + json; the signature is not checked. Never cached past one use.
    - `async t4_login_slot() -> None`: books one budget slot for a T4 socket login (`blocked` → `LoginDeferred`).
    - `async aclose()`.

- [ ] **Step 1: Write the failing tests** (an `httpx.MockTransport` fake of Alpha):
  - `test_login_posts_email_and_password_and_keeps_tokens_in_memory`: the body equals `{"email": "o@x.com", "password": "pw"}`, and `secrets_store` holds no token after.
  - `test_wrong_password_raises_AtrLoginFailed_without_the_password`.
  - `test_a_code_step_raises_NeedsCode`: the answer has an `mfa`/`verify` marker (constant `CODE_MARKERS`, unconfirmed).
  - `test_access_renews_by_refresh_without_a_budget_slot`: 0 password logins, 0 budget records.
  - `test_expired_refresh_falls_back_to_one_password_login_through_the_budget` (Review Focus 5): exactly 1 password login. With the budget spent → `LoginDeferred`, 0 logins.
  - `test_t4_creds_decodes_the_jwt_payload_and_repr_hides_the_password`: `"t4pw" not in repr(creds)`.
  - `test_t4_login_slot_books_the_budget`.
  - `test_nothing_secret_in_repr_or_errors`: no password, token or JWT in `repr(session)` or in any raised message.
- [ ] **Step 2: Run** `pytest tests/test_alphatrader_auth.py -q` → FAIL.
- [ ] **Step 3: Implement**, shaped like `topstepx_auth.TsxSession`.
- [ ] **Step 4: Run** `pytest tests/test_alphatrader_auth.py tests/test_topstepx_auth.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "alphatrader: the login session (email + password, refresh, T4 credentials, budget)"`.

### Task 3: The T4 socket (`AtrSocket`)

**Files:**
- Create: `homebase/broker/alphatrader_ws.py`
- Test: `tests/test_alphatrader_ws.py`

**Interfaces:**
- Consumes: `AtrSession.t4_creds()`, `t4_login_slot()`, `lock`; `alphatrader_proto.client/server`; `WS_URL`.
- Produces:
  - `class AtrSocket(session: AtrSession, on_event: Callable[[str, dict], None], *, url: str = WS_URL, on_up: Callable[[], Awaitable[None]] | None = None, on_taken: Callable[[str], Awaitable[None]] | None = None)`.
  - `async start()`, `async stop()`, `up: bool` (true only after `loginResponse.result == 0`), `async send(payload: str, data: dict) -> None` (raises `ConnectionError` when not up).
  - On each connect, under `session.lock`: `t4_login_slot()`, then `t4_creds()`, then `loginRequest`. On success: `accountSubscribe`, `up = True`, `await on_up()`.
  - Heartbeat: send every `HEARTBEAT_S = 20`. If nothing arrives for `SILENT_S = 60`, close and reconnect.
  - `loginResponse.result == 6`, or `7` after being up: `up = False`, then `await on_taken("logged in elsewhere")`, and the socket logs in again at once. The budget makes it wait when it is spent. A result of 1/9/18: stop, `session.lost = <words>`, no retry loop. A result of 24: `session.lost = "AlphaTrader needs a code"`, stop.
  - Reconnect after a drop: waits 1 s, 2 s, 4 s, 8 s, then 15 s steps. It goes back to 1 s after `STABLE_S = 10` up.
  - Every other payload goes to `on_event(payload_name, dict)`. Heartbeats are not forwarded.

- [ ] **Step 1: Write the failing tests** against a local `websockets.serve` on 127.0.0.1 that speaks the codec:
  - `test_login_then_account_subscribe_are_sent_and_up_after_success`.
  - `test_payloads_reach_on_event_and_heartbeats_do_not`.
  - `test_logged_in_elsewhere_calls_on_taken_and_logs_in_again_once`: 2 T4 logins, 2 budget slots.
  - `test_logged_in_elsewhere_with_the_budget_spent_waits_and_sets_lost`.
  - `test_a_failed_login_stops_without_a_loop`: 1 login only, `session.lost` set.
  - `test_sixty_seconds_of_silence_reconnects` (patch `SILENT_S` small).
  - `test_send_when_down_raises_ConnectionError`.
  - `test_no_credential_reaches_the_log`: capture stderr and logging; the T4 password and username are absent.
- [ ] **Step 2: Run** `pytest tests/test_alphatrader_ws.py -q` → FAIL.
- [ ] **Step 3: Implement**, shaped like `topstepx_ws.TsxHub`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "alphatrader: the T4 socket (login, heartbeat, kick, reconnect through the budget)"`.

### Task 4: The adapter: accounts, markets, caches

**Files:**
- Create: `homebase/broker/alphatrader.py`
- Test: `tests/test_alphatrader_adapter.py`

**Interfaces:**
- Consumes: Tasks 1–3; `BrokerAdapter`, `OrderRequest`, `OrderResult`, `AccountNotOnLogin`, `FillEvent`, `FillCallback` (`homebase/broker/base.py`); `symbols.front_month`.
- Produces:
  - `class AlphaTraderAdapter(BrokerAdapter)`, `platform = "alphatrader"`, with
    `__init__(account_id: str, *, keyring_key: str, account_name: str, session: AtrSession, live: bool = False)`.
  - Constants: `EXCHANGE = {"NQ": "CME_Eq", "MNQ": "CME_Eq", "ES": "CME_Eq", "MES": "CME_Eq", "GC": "CME_CO", "MGC": "CME_CO"}`,
    `TICK` (as TopstepX), `ATR_BOOKING_OPEN = False`,
    `ATR_BOOKING_CLOSED = "AlphaTrader accounts can't be booked yet: waiting for the read-only check and the first watched order"`,
    `STOP_GRACE_S = 2.0`, `ATR_FLATTEN_IF_NO_STOP = False`, `ORDER_WAIT_S = 5.0`, `PRACTICE_MODES` / `PRACTICE_WORDS`
    (marked `# unconfirmed`: how an evaluation account is marked; default: the display name or group contains "eval" or "practice").
  - One `AtrSocket` per session, held on `session.socket` and created by the first adapter. Events fan out to every adapter on that login, each keeping only its own `accountId`.
  - `async connect()`: the socket comes up (it waits for `up` up to 15 s), then the account is picked from `loginResponse.accounts` / `accountDetails` by name (case-insensitive) or by id. `account_name == ""` means a probe that only lists. A missing name raises `AccountNotOnLogin`.
  - `list_accounts() -> list[dict]`: `[{"id", "name", "active", "practice": bool}]`.
  - `async market_id(symbol: str, today: dt.date | None = None) -> str`: the front month from `symbols.front_month` (or an explicit `NQZ26`), resolved through `GET /api/v1/market/symbols/` and cached per root+month. Fields `SYM_MARKET_FIELD` etc. are `# unconfirmed`. An unknown root, or no matching row, raises `ValueError`.
  - Caches, fed by `on_event` and by `accountSnapshot` messages: positions per `marketId` (`net = buys - sells`, `# unconfirmed`); orders per `uniqueId` (status, side, price type, prices, volume, tag, `ClOrdId`, `orderLink`, `ordersLinked`); balance from `accountUpdate.balance`. `positions_known` / `orders_known` are False until the first `accountSnapshot`, and False while a market is dirty (a fill seen, its position not yet).
  - `async get_net_position(symbol) -> int`: the sum over every market of that root. Raises `RuntimeError("position unknown")` while not known.
  - `async get_balance() -> dict`, `async get_metrics() -> dict` (base keys + `session_taken`, `no_stop`).

- [ ] **Step 1: Write the failing tests** (a fake `AtrSocket` that records sends and lets the test push events; a MockTransport for `/market/symbols/`):
  - `test_connect_picks_the_named_account_and_a_missing_name_raises_AccountNotOnLogin`.
  - `test_list_accounts_marks_practice_rows`.
  - `test_two_adapters_on_one_login_share_one_socket_and_each_keeps_its_own_account_events`.
  - `test_market_id_resolves_the_front_month_and_caches_it`: one REST call for two lookups.
  - `test_snapshot_seeds_positions_and_net_sums_every_month_of_a_root` (Review Focus 4: a Z26 and an H27 row both count).
  - `test_net_position_raises_while_unknown_or_dirty`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "alphatrader: the adapter (accounts, markets, caches; unknown is never flat)"`.

### Task 5: Orders, brackets, cancel, flatten

**Files:**
- Modify: `homebase/broker/alphatrader.py`
- Test: `tests/test_alphatrader_adapter.py` (add)

**Interfaces:**
- Produces: `async place_order(req)`, `async place_bracket(req)`, `async cancel_order_by_id(order_id)`, `async cancel_all()`,
  `async flatten_all()`, `async flatten_symbol(symbol)`. Each returns `OrderResult`. A bracket result's `raw` has
  `sl_order_id` / `tp_order_id`: the leg `uniqueId`s, filled in from the order updates once known.
- Rules:
  - Each order gets `ClOrdId = f"HB_{uuid4().hex}"` and `tag = req.text[:40]`. `manualOrderIndicator = False`. `timeType` NORMAL for the entry.
  - Entry types: Market → MARKET; Limit → LIMIT + `limitPrice`; Stop → STOP_MARKET + `stopPrice`; StopLimit → STOP_LIMIT + both prices.
  - A bracket is the Facts' three-order AUTO_OCO_P submit. The target is left out when `tp_price` is None. A stop on the profit side of the reference price is refused, and nothing is sent. The reference is `req.price` (Limit or Stop), `req.trigger_price` (StopLimit) or `req.price` (Market, needed; None → refused: `"alphatrader: a bracketed market entry needs a price"`).
  - The answer: wait up to `ORDER_WAIT_S` for the `orderUpdate*` whose `tagClOrdId` is the entry's `ClOrdId`. WORKING, HELD or FINISHED → `ok=True` with the `uniqueId`. REJECTED or `orderUpdateFailed` → `ok=False` with `statusDetail`. No answer → `ok=False, raw={"outcome_unknown": True}`, never resent. A late answer still fills the cache (Review Focus 3).
  - Cancel: an `orderPull` per working order, with that order's `marketId`. `cancel_all` pulls every working order of this account.
  - Flatten (with the TopstepX parked fixes):
    - Read positions first, and refuse while they are unknown.
    - For each held market, send an opposite MARKET order of `|net|`.
    - Then pull the working orders of the markets that closed. A refused close on one market does not skip the other markets' pulls.
    - Re-close only when the net flips sign.
  - The socket is down → `OrderResult(ok=False, error="alphatrader: not connected")`, nothing queued.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_buy_limit_bracket_is_one_submit_with_three_orders_auto_oco_p`: NQ buy limit 20000, stop 19990, target 20020. Exactly one `orderSubmit`; `orderLink 7`; `orders[1]` is SELL LIMIT GTC volume 0 limit 20020 HOLD; `orders[2]` is SELL STOP_MARKET GTC volume 0 stop 19990 HOLD.
  - `test_a_sell_stop_entry_bracket_legs_are_buys`.
  - `test_a_bracketed_market_entry_without_a_price_is_refused_and_nothing_is_sent`.
  - `test_a_stop_on_the_wrong_side_is_refused`.
  - `test_the_answer_is_matched_by_ClOrdId_and_a_reject_carries_T4s_words`.
  - `test_no_answer_is_outcome_unknown_never_resent_and_a_late_update_is_cached`.
  - `test_bracket_leg_ids_are_recorded_from_order_updates`.
  - `test_flatten_reads_positions_first_closes_each_month_then_pulls_only_closed_markets`.
  - `test_a_refused_close_on_one_month_still_pulls_the_other_months_orders`.
  - `test_flatten_refuses_while_positions_are_unknown`.
  - `test_cancel_all_pulls_only_this_accounts_working_orders`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "alphatrader: orders with the bracket in the same submit, cancel, flatten (TopstepX lessons in)"`.

### Task 6: Fills, the no-stop guard, taking the session back

**Files:**
- Modify: `homebase/broker/alphatrader.py`
- Test: `tests/test_alphatrader_adapter.py` (add)

**Interfaces:**
- Produces:
  - `async observe_fills(on_fill)`: each `orderUpdateTrade`, and each `orderUpdate.trades[]` entry, for this account becomes one `FillEvent(account_id, symbol=<root>, side, qty, price, position_after, ts, raw)`. The side comes from the order cache's `buySell`. Each `(uniqueId, sequenceOrder)` or `exchangeTradeId` is reported once (a bounded seen-set, `_SEEN_FILL_CAP = 20000`). Fills from orders Homebase did not send (Alpha's own closes, a hand trade) are reported the same way.
  - `self._notify(...)` with the base types `order` / `position` / `fill`, as TopstepX does.
  - The no-stop guard (TopstepX's, with its parked fixes):
    - After a fill, wait `STOP_GRACE_S`. If the market still holds a position, look for a working or held STOP_MARKET on the other side covering `|net|`. If none is seen: add the market to `_no_stop` and journal `atr_no_stop_seen`. Only when `ATR_FLATTEN_IF_NO_STOP` is on, flatten it and journal `atr_no_stop_flatten`.
    - A stop that arrives later clears the flag.
    - Never acts while `orders_known` is False.
    - The stop check compares size.
  - Session taken (`on_taken`): `session.taken += 1`; journal `atr_session_taken` (account, count, why); the card shows `session.lost` until the socket is back. On `on_up` after a reconnect, the next `accountSnapshot` reseeds the caches and replays unseen fills once. The order cache is reseeded while it is unknown.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_trade_becomes_one_FillEvent_and_a_repeat_or_snapshot_replay_is_ignored`.
  - `test_another_accounts_trade_is_ignored`.
  - `test_an_outside_fill_is_reported`.
  - `test_no_stop_after_grace_journals_and_does_not_flatten_while_the_switch_is_off`.
  - `test_a_late_stop_clears_the_no_stop_flag`.
  - `test_no_stop_check_waits_while_orders_are_unknown`.
  - `test_a_stop_smaller_than_the_position_counts_as_no_stop`.
  - `test_session_taken_journals_logs_in_again_once_and_replays_the_gap_fill_once` (Review Focus 2).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `pytest tests/test_alphatrader_*.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "alphatrader: fills, the no-stop guard, a kicked session taken back through the budget"`.

### Task 7: Desk wiring and the connect routes

**Files** (each change mirrors its TopstepX line beside it):
- Modify `homebase/desk_app/brokers.py`:
  - `NEEDS_CODE_ATR = "AlphaTrader needs a code"`, `_ATR_SESSIONS`, `is_atr_key()`, `atr_session()`.
  - `_key_env` → `"atr"`.
  - `md_source` skips `atr:` keys.
  - `build_adapter` makes an `AlphaTraderAdapter`.
  - `_login_label` → `"AlphaTrader"`.
  - `_connect_account_locked` sets `ad.journal`, `ad.session.budget` and `ad.session.journal`, and treats a held session like TopstepX at lines 251–273.
  - The rebook at line 316: `ATR_BOOKING_OPEN or not is_atr_key(key)`.
  - `NeedsCode` → `atr_needs_code`.
  - A lost session shows disconnected with its reason (line 554).
- Modify `homebase/routes/accounts.py`:
  - `/api/logins`: the label is the email.
  - `/api/connect`: `broker == "atr"` or a saved `atr:` key gives key `atr:<email lower>`. `code` goes to the probe's `login`. `NeedsCode` → `{"ok": False, "needs_code": True, "key": key}`. Success → `"env": "atr"`.
  - `add-many`: an `atr:` row gets `live = not practice`.
- Modify `homebase/routes/strategies.py:139`: the same refusal with `alphatrader.ATR_BOOKING_OPEN` / `ATR_BOOKING_CLOSED` for `atr:` accounts.
- Test: `tests/test_alphatrader_routes.py`, copying the shape of `tests/test_topstepx_routes.py`.

- [ ] **Step 1: Write the failing tests:**
  - `test_connect_with_broker_atr_saves_atr_key_and_lists_accounts`.
  - `test_connect_goes_through_the_login_budget`.
  - `test_needs_code_answers_needs_code_true`.
  - `test_add_many_marks_practice_demo_and_the_rest_live`.
  - `test_build_adapter_makes_an_AlphaTraderAdapter_sharing_one_session_per_login`.
  - `test_md_source_never_picks_an_atr_login`.
  - `test_booking_an_atr_account_is_refused_with_ATR_BOOKING_CLOSED`.
  - `test_a_restore_does_not_rebook_an_atr_account`.
  - `test_logins_lists_atr_with_env_atr`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_alphatrader_routes.py tests/test_topstepx_routes.py tests/test_add_accounts.py tests/test_vest_routes.py tests/test_account_gone.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "desk: AlphaTrader logins in the connect routes and the broker builder; booking refused"`.

### Task 8: The wizard option

**Files:**
- Modify `homebase/static/index.html`:
  - Step 1: `<div class="opt" id="optAtr" onclick="wizBroker('atr')">`, glyph `At`, title `AlphaTrader`, sub `Alpha Futures · email & password`.
  - Step 2: the email goes in `#cUser`, whose label reads "Email" when `atr` is picked.
  - Reuse `#cCodeRow`; its label becomes `Code from AlphaTrader` when `atr` is picked.
  - Bump the `book.js` cache version.
- Modify `homebase/static/desk/book.js`:
  - `wizBroker("atr")`: `#envSeg` hidden, heading `Log in to AlphaTrader`, note text `"An AlphaTrader login lists every Alpha account under it. Nothing trades until you assign it to a strategy."`.
  - `doConnect` sends `{broker: "atr", username: <email>, password, code?}`.
  - `needs_code` → show the code row and toast `"AlphaTrader sent you a code — type it in"`.
  - `env "atr"` → the saved-login label `AlphaTrader`.
  - Account rows show `practice` / `funded`.
  - Close clears the password and the code.
- Modify `tests/test_desk_page.py` `DESK_PINS` for the new `book.js` version and hash.
- Test: `tests/test_alphatrader_wizard.py` (the `tests/test_topstepx_wizard.py` pattern).

- [ ] **Step 1: Write the failing tests:**
  - `test_step_1_offers_alphatrader`.
  - `test_the_env_switch_is_hidden_for_atr`.
  - `test_doConnect_sends_broker_atr_and_the_code`.
  - `test_the_password_and_code_are_cleared_on_close`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_alphatrader_wizard.py tests/test_topstepx_wizard.py tests/test_desk_page.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "desk: the AlphaTrader option in the add-account wizard"`.

### Task 9: Whole-branch check, then the owner's steps

- [ ] **Step 1: Run** `pytest tests -q` without `-x`. Every failure must also fail on `main` (known: `test_backtest_montecarlo` timing, `test_charts_news_server` fan-out, `test_charts_js`).
- [ ] **Step 2: Whole-branch review** by a fresh reviewer, against the spec and this plan.
- [ ] **Step 3: (Owner, once he owns an AlphaTrader account.)** Run `.spike/atr_spike.py`. Correct the `# unconfirmed` constants and the spec's facts from its printout. Commit.
- [ ] **Step 4: (Owner, read only.)** Start the Mac desk from this worktree. The owner adds his login in the wizard and ticks an evaluation account. Check that the card shows the balance and the position, and that the journal has `broker_connected`.
- [ ] **Step 5: (Only on the owner's word, with him watching.)** One MNQ limit bracket far from the price, then cancel it. Check that the stop and target show on AlphaTrader as held legs.
- [ ] **Step 6:** Lift `ATR_BOOKING_OPEN`, and merge to `main`, only when the owner says so.
