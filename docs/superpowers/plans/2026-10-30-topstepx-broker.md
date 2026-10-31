# TopstepX Broker Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A TopstepX account can be added from the desk wizard with a TopstepX username + password, and trades like a Tradovate account.

**Architecture:** One `TsxSession` per TopstepX login (token, re-login through the login budget) and one SignalR account socket per
login, shared by every desk entry on that login (the Vest pattern: `brokers._TSX_SESSIONS`). `TopstepXAdapter` (one per desk entry)
speaks TopstepX's own web calls on `https://userapi.topstepx.com`. The desk routes and wizard reuse the Tradovate username/password
path with a `tsx:` login key.

**Tech Stack:** Python 3, `httpx` (REST), `websockets` (SignalR JSON protocol by hand), FastAPI routes, plain JS in `homebase/static`.

**Spec:** `docs/superpowers/specs/2026-10-30-topstepx-broker-design.md` (approved 2026-10-30).

## Global Constraints

- Work only on `feat/topstepx` in `.worktrees/topstepx`. Never merge to `main` (main ships to the live VPS by itself) until the owner says so.
- No new dependency. `httpx`, `websockets` are already in `requirements.txt`.
- Login key: `tsx:<username lowercased>`; `secrets_store.set_credentials(key, username=..., password=...)`. The token lives in memory only.
- The password, the token and the `Authorization` header never reach a log line, the journal, an exception message or git.
- Every TopstepX login (first, re-login after a 401, after a kick) goes through the `LoginBudget` (`homebase/broker/login_budget.py`).
- Every entry that has a stop sends it on the entry order itself (`stopLoss`), never as a later separate order.
- Tests never reach the network: `tests/conftest.py`'s guard covers `test_topstepx*` files too.
- Shell hooks block commands mentioning order-placing words; read broker files with the Read tool, not `sed`/`grep` pipelines on them.

## Facts from TopstepX's site code (2026-10-30), to confirm in Task 1

| What | Value |
|---|---|
| REST base | `https://userapi.topstepx.com` (from `https://topstepx.com/config.json`, `userApi`) |
| Login | `POST /Login` `{"userName", "password"}` → token (field name: spike) + `userId`, `result`, `errorMessage` |
| Check session | `GET /Session/validate` |
| Accounts | `GET /TradingAccount` |
| Order | `POST /Order` `{accountId, symbolId, contractId, type, positionSize, limitPrice, stopPrice, customTag, timeType, stopLoss, takeProfit}` |
| Order `type` | Limit=1, Market=2, StopLimit=3, Stop=4, TrailingStop=5 |
| Side | the sign of `positionSize`: + buy, − sell (spike confirms) |
| Bracket | `stopLoss` / `takeProfit` = `{"ticks": int, "type": 0}` (0 = ticks, 1 = dollars), measured from the fill |
| Cancel | `/Order/cancel/{accountId}/id/{orderId}`, `/Order/cancel/{accountId}/all` |
| Flatten | `/Position/close/{accountId}` (all), `/Position/close/{accountId}/contract/{contractId}` |
| Reads | `/Position/all/account/{accountId}`, `/Trade/id/{accountId}` |
| Socket | `wss://userapi.topstepx.com/hubs/account?access_token=<token>`, SignalR JSON, `skipNegotiation`; invoke `SubscribeAccounts`; pushes `RealTimeOrder`, `RealTimePosition`, `RealTimeTrade`, `RealTimeAccount`, `RealTimeSession`, `RealTimeTradingAccountViolation` |
| Contract ids | `CON.F.US.<code>.<month letter><2-digit year>`, e.g. `CON.F.US.ENQ.Z26`; codes NQ→ENQ, MNQ→MNQ, ES→EP, MES→MES, GC→GCE, MGC→MGC (spike confirms) |
| Tick size | NQ/MNQ/ES/MES 0.25, GC/MGC 0.10 |

All of these live as named constants at the top of `topstepx_auth.py` / `topstepx.py`, so the spike's corrections touch one place.

## Review Focus

1. **A market entry with a stop but no reference price.** Expect: refused with `"topstepx: a bracketed market entry needs a price"`, nothing sent. (Task 4 test.)
2. **A stop more than 0 but less than one tick from the entry, or on the wrong side.** Expect: ticks rounded away from the entry to at least 1; a stop on the wrong side refused. (Task 4 test.)
3. **The owner opens TopstepX while a position is open.** Expect: the socket's session ends, `tsx_session_taken` is journaled, one re-login through the budget, the socket comes back, fills during the gap are found by a `/Trade/id` read after reconnect. (Task 5 test.)
4. **A login refused by the budget mid-kick (hourly cap reached).** Expect: no login sent, the account card shows the budget's reason, the next try waits for the budget. (Task 2 test.)
5. **The order call times out after sending.** Expect: the adapter looks the order up by its `customTag` before answering; not found → `outcome_unknown`, never a resend. (Task 4 test.)

---

### Task 1: Read-only spike with the owner's login

**Files:**
- Create (not committed): `.worktrees/topstepx/.spike/tsx_spike.py`

**Interfaces:**
- Produces: the confirmed values for the facts table, written into the spec's "What we know" section.

- [ ] **Step 1: Write the spike script.** It asks for the username with `input()` and the password with `getpass.getpass()` (the owner types them; nothing is saved), then, read only: `POST /Login`, prints the answer's KEYS and `result`/`errorMessage` (never the token); decodes the token's JWT `exp` and prints the lifetime in minutes; `GET /TradingAccount` → prints each row's keys and the `name`/`id`/balance-like fields; `GET /Position/all/account/{id}` for the first account → keys; opens the socket, sends the handshake, invokes `SubscribeAccounts`, prints each frame's `target` and its argument's keys for 60 s.
- [ ] **Step 2: The owner runs it** (`python3 .spike/tsx_spike.py`, in his own terminal). Paste back the printout. If `/Login` asks for a code, note the field name and how the code arrives.
- [ ] **Step 3: Update the spec's facts and this plan's facts table** with what the printout shows (token field, lifetime, account fields incl. how a practice account is marked, socket host and frame shapes). Commit the spec change.

```bash
git add docs/superpowers/specs/2026-10-30-topstepx-broker-design.md docs/superpowers/plans/2026-10-30-topstepx-broker.md
git commit -m "spec: TopstepX facts confirmed by the read-only spike"
```

### Task 2: The login session (`TsxSession`)

**Files:**
- Create: `homebase/broker/topstepx_auth.py`
- Modify: `tests/conftest.py` (the network guard: `request.path.name.startswith(("test_vest", "test_topstepx"))`, message words "Vest/TopstepX tests")
- Test: `tests/test_topstepx_auth.py`

**Interfaces:**
- Produces:
  - `BASE = "https://userapi.topstepx.com"`, `HUB_URL = "wss://userapi.topstepx.com/hubs/account"`, `RENEW_LEFT_S = 600`
  - `class NeedsCode(RuntimeError)` — TopstepX wants a one-time code for this login.
  - `class TsxLoginFailed(RuntimeError)` — wrong username/password; message is TopstepX's `errorMessage` (never the password).
  - `class TsxSession(key: str, *, http: httpx.AsyncClient | None = None, budget: LoginBudget | None = None)`
    - `async login(code: str | None = None) -> None` — reads `secrets_store.get_credentials(key)`; posts `/Login`; keeps `token`, `user_id`, `expires_at` (JWT `exp`, else now + 23 h).
    - `async token() -> str` — renews (`login()` through the budget) when under `RENEW_LEFT_S` left.
    - `async request(method: str, path: str, **kw) -> httpx.Response` — bearer added; on 401: `relogin("401")` once, then retry once.
    - `async relogin(why: str) -> None` — `budget.blocked(key)` → raises `LoginDeferred(reason)` (`homebase/broker/login_budget.py`); else `record_login`, `login()`, `login_result`.
    - `taken: int` — how many times TopstepX ended the session (Task 5 adds to it); `user_id: int | None`.
    - `async aclose() -> None`.

- [ ] **Step 1: Write the failing tests** (an `httpx.MockTransport` fake of `/Login`, `/TradingAccount`):
  - `test_login_posts_username_and_password_and_keeps_the_token_in_memory` — body `== {"userName": "Owner", "password": "pw"}`; `secrets_store.get_credentials(KEY)` has no token key after.
  - `test_a_wrong_password_raises_TsxLoginFailed_with_topstepx_words_not_the_password` — `"pw" not in str(err)`.
  - `test_a_code_request_raises_NeedsCode` (answer shape from Task 1).
  - `test_request_sends_the_bearer_and_a_401_relogs_in_once_then_retries` — 2 `/Login` calls total, the retried call answered 200; a second 401 is returned, not looped.
  - `test_relogin_refused_by_the_budget_sends_no_login` — budget with the hourly cap spent → `LoginDeferred`, 0 `/Login` calls.
  - `test_token_renews_when_under_ten_minutes_left`.
  - `test_nothing_secret_in_repr_or_errors` — `repr(session)` and every raised message contain neither the password nor the token.
- [ ] **Step 2: Run** `pytest tests/test_topstepx_auth.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement `topstepx_auth.py`** following `vest_auth.VestSession`'s shape (one `httpx.AsyncClient`, `Origin`/`Referer` `https://topstepx.com`, a browser `User-Agent` as in `tradovate_auth.USER_AGENT`).
- [ ] **Step 4: Run** `pytest tests/test_topstepx_auth.py tests/test_vest_auth.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "topstepx: the login session (username + password, renew, 401 re-login through the budget)"`.

### Task 3: The account socket (SignalR, by hand)

**Files:**
- Create: `homebase/broker/topstepx_ws.py`
- Test: `tests/test_topstepx_ws.py`

**Interfaces:**
- Consumes: `TsxSession.token()`, `TsxSession.relogin()`, `HUB_URL`.
- Produces: `class TsxHub(session: TsxSession, on_event: Callable[[str, dict], None], *, url: str = HUB_URL, on_up: Callable[[], Awaitable[None]] | None = None)`
  - `async start() -> None` / `async stop() -> None`; `up: bool`.
  - Frames end with `"\x1e"`. On open: send `{"protocol":"json","version":1}\x1e`, then invoke `SubscribeAccounts` (type 1, no args).
  - Type 1 frames → `on_event(target, arg)` for each argument dict; type 6 → answer `{"type":6}`; type 7 → close, then reconnect.
  - Reconnect waits 0.2 s, 1.5 s, 3 s, then 5 s steps (the site's own schedule); a 401 at open → `session.relogin("socket 401")` first. After every reconnect: `await on_up()` (Task 5 re-reads trades there).

- [ ] **Step 1: Write the failing tests** against a local `websockets.serve` on 127.0.0.1:
  - `test_handshake_then_SubscribeAccounts_is_sent`.
  - `test_invocations_reach_on_event_and_pings_are_answered` — two records in one message both delivered.
  - `test_a_close_frame_reconnects_and_calls_on_up`.
  - `test_a_401_at_open_relogs_in_through_the_session_once`.
  - `test_the_token_is_never_logged` — capture stderr; the token string absent.
- [ ] **Step 2: Run** `pytest tests/test_topstepx_ws.py -q` → FAIL.
- [ ] **Step 3: Implement `topstepx_ws.py`.** The token rides as `?access_token=` (what the browser's SignalR client does with `skipNegotiation`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "topstepx: the account socket (SignalR JSON, reconnect, 401 re-login)"`.

### Task 4: The adapter — accounts and orders

**Files:**
- Create: `homebase/broker/topstepx.py`
- Test: `tests/test_topstepx_adapter.py`

**Interfaces:**
- Consumes: `TsxSession`, `TsxHub`, `BrokerAdapter`, `OrderRequest`, `OrderResult`, `AccountNotOnLogin` (`homebase/broker/base.py`), `symbols.front_month`, `contracts.root_of`.
- Produces: `class TopstepXAdapter(BrokerAdapter)`, `platform = "topstepx"`,
  `__init__(account_id: str, *, keyring_key: str, account_name: str, session: TsxSession, live: bool = False)`
  - `async connect()` — `session.token()`; `GET /TradingAccount`; `account_name == ""` is a probe (lists only); else pick the row whose name matches (case-insensitive) or raise `AccountNotOnLogin`; start the login's shared `TsxHub` (one per session: `session.hub`).
  - `list_accounts() -> list[dict]` — `[{"id", "name", "active", "practice": bool}]` (same keys as Tradovate's plus `practice`).
  - `contract_id(symbol: str) -> str` — `CON.F.US.<CODES[root]>.<letter><yy>` from `symbols.front_month(root)`; unknown root → `ValueError`.
  - `async place_order(req)`, `async place_bracket(req)`, `async cancel_order_by_id(order_id)`, `async cancel_all()`, `async flatten_all()`, `async flatten_symbol(symbol)`, `async get_net_position(symbol) -> int`, `async get_balance() -> dict`, `async get_metrics() -> dict` (the base keys), `async close()` (stops nothing shared).
  - Constants: `CODES = {"NQ": "ENQ", "MNQ": "MNQ", "ES": "EP", "MES": "MES", "GC": "GCE", "MGC": "MGC"}`, `TICK = {"NQ": .25, "MNQ": .25, "ES": .25, "MES": .25, "GC": .1, "MGC": .1}`, `TYPE = {"Limit": 1, "Market": 2, "StopLimit": 3, "Stop": 4}`.
- Order body rules:
  - `positionSize = qty` for Buy, `-qty` for Sell. `customTag = f"{req.text}:{uuid4().hex[:12]}"` (unique per order).
  - Limit: `limitPrice=price`. Stop (no bracket): `stopPrice=req.stop_price`. Stop entry in a bracket: `stopPrice=req.price`. StopLimit: `limitPrice=price`, `stopPrice=trigger_price`.
  - Bracket: reference = `req.price` (Limit/Stop) or `req.trigger_price` (StopLimit) or `req.price` (Market; None → refused, Review Focus 1). `stopLoss = {"ticks": ceil(|ref − stop| / tick), "type": 0}` (at least 1), the same for `takeProfit` with `tp_price`; a stop on the profit side of `ref` → refused.
  - A timeout or drop after sending: `GET` the account's orders, match `customTag`; found → that order's result; not found → `OrderResult(ok=False, raw={"outcome_unknown": True}, error=...)`. Never resend.
  - Prices are rounded to the root's tick.

- [ ] **Step 1: Write the failing tests** (MockTransport fake of the REST calls; a stub `TsxHub` that records nothing):
  - `test_connect_picks_the_named_account_and_a_missing_name_raises_AccountNotOnLogin`.
  - `test_list_accounts_marks_practice_rows` (marker from Task 1).
  - `test_contract_id_for_nq_es_gc_front_months` — e.g. NQ on 2026-10-30 → `"CON.F.US.ENQ.Z26"`.
  - `test_a_buy_limit_bracket_sends_one_order_with_stopLoss_and_takeProfit_in_ticks` — NQ buy limit 20000, stop 19990, tp 20020 → `positionSize 1, type 1, limitPrice 20000, stopLoss {"ticks": 40, "type": 0}, takeProfit {"ticks": 80, "type": 0}`; exactly one `POST /Order`.
  - `test_a_sell_stop_entry_bracket` — sign −, `type 4`, `stopPrice = req.price`.
  - `test_a_bracketed_market_entry_without_a_price_is_refused_and_nothing_is_sent`.
  - `test_a_stop_on_the_wrong_side_is_refused_and_a_sub_tick_stop_rounds_to_one_tick`.
  - `test_a_timeout_after_send_finds_the_order_by_customTag_and_never_resends`; `..._not_found_is_outcome_unknown`.
  - `test_flatten_all_and_cancel_all_call_close_and_cancel_all_for_this_account_only`.
- [ ] **Step 2: Run** `pytest tests/test_topstepx_adapter.py -q` → FAIL.
- [ ] **Step 3: Implement `topstepx.py`** (accounts + orders; fills come in Task 5).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `git commit -m "topstepx: the adapter (accounts, contract ids, orders with the stop on the entry, flatten, cancel)"`.

### Task 5: Fills, positions and taking the session back

**Files:**
- Modify: `homebase/broker/topstepx.py`
- Test: `tests/test_topstepx_adapter.py` (add)

**Interfaces:**
- Consumes: `TsxHub` events; `FillEvent`, `FillCallback`.
- Produces:
  - `async observe_fills(on_fill: FillCallback) -> None` — `RealTimeTrade` rows for this account → `FillEvent(account_id, symbol=<root>, side, qty, price, position_after, ts, raw)`, each trade id once (a bounded seen-set, like `_SEEN_FILL_CAP` in `tradovate.py`).
  - `RealTimePosition` → a per-contract net cache read by `get_net_position` (REST `/Position/all/account/{id}` only when the cache was never seeded); `RealTimeOrder` / `RealTimePosition` / `RealTimeTrade` → `self._notify(...)` with the base types `order` / `position` / `fill`.
  - Session taken: a `RealTimeSession` push that ends this session, or the socket closing with an auth error → `session.taken += 1`, `self.journal("tsx_session_taken", account=..., count=...)` (journal is set by the desk, as for Vest), then `session.relogin("taken")` at once (budget-capped) and the hub restarts. `on_up` reads `/Trade/id/{accountId}` and feeds trades not yet seen to `on_fill` (fills during the gap).
  - `get_metrics()` adds `"session_taken": session.taken`.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_trade_push_becomes_one_FillEvent_and_a_repeat_is_ignored`.
  - `test_another_accounts_trade_is_ignored`.
  - `test_position_push_updates_get_net_position_without_a_rest_call`.
  - `test_session_taken_journals_relogs_in_once_and_replays_missed_trades` — Review Focus 3: one `/Login`, one `tsx_session_taken`, the gap trade delivered once.
  - `test_session_taken_with_the_budget_spent_does_not_log_in_and_says_why` — Review Focus 4.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_topstepx_adapter.py tests/test_topstepx_ws.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "topstepx: fills and positions from the socket; a kicked session is taken back through the budget"`.

### Task 6: Desk wiring and the connect routes

**Files:**
- Modify: `homebase/desk_app/brokers.py` (`is_tsx_key`, `tsx_session`, `_TSX_SESSIONS`, `_key_env` → `"tsx"`, `build_adapter`, `md_source` skips `tsx:` keys, `_login_label` → `"TopstepX"`, `_connect_account_locked` sets `ad.journal` and `ad.session.budget` for a `TopstepXAdapter`, `_connect_failed` shows `"TopstepX needs a code"` for `NeedsCode`)
- Modify: `homebase/routes/accounts.py` (`/api/logins` label = the username; `/api/connect`: `broker == "tsx"` or a `tsx:` saved key → key `tsx:<username lower>`, `code` passed to the probe's `login`, `NeedsCode` → `{"ok": False, "needs_code": True, "key": key}`; `/api/accounts/add-many`: a `tsx:` row's `live = not practice` from `_listed`)
- Test: `tests/test_topstepx_routes.py`

**Interfaces:**
- Consumes: Tasks 2–5.
- Produces: `/api/connect` body `{"broker": "tsx", "username", "password", "code"?}` or `{"saved_key": "tsx:..."}` → `{"ok", "key", "env": "tsx", "accounts"}`; the wizard (Task 7) relies on `needs_code`.

- [ ] **Step 1: Write the failing tests** (the app's routes with a fake `adapter_factory`, the patterns of `tests/test_vest_routes.py` and `tests/test_add_accounts.py`):
  - `test_connect_with_broker_tsx_saves_tsx_key_and_lists_accounts`.
  - `test_connect_goes_through_the_login_budget` — cap spent → `ok False` with the budget's words, no login.
  - `test_needs_code_answers_needs_code_true`.
  - `test_add_many_marks_practice_demo_and_the_rest_live`.
  - `test_build_adapter_makes_a_TopstepXAdapter_sharing_one_session_per_login`.
  - `test_md_source_never_picks_a_tsx_login`.
  - `test_logins_lists_tsx_with_env_tsx`.
- [ ] **Step 2: Run** `pytest tests/test_topstepx_routes.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_topstepx_routes.py tests/test_add_accounts.py tests/test_vest_routes.py tests/test_vest_wiring.py tests/test_account_gone.py -q` → PASS.
- [ ] **Step 5: Commit** `git commit -m "desk: TopstepX logins in the connect routes and the broker builder"`.

### Task 7: The wizard option

**Files:**
- Modify: `homebase/static/index.html` (step 1: `<div class="opt" id="optTsx" onclick="wizBroker('tsx')">`, glyph `Tx`, title `TopstepX`, sub `Username & password`; step 2: an `id="cCodeRow"` field, hidden, label `Code from TopstepX`, input `id="cCode"`)
- Modify: `homebase/static/desk/book.js` (`wizBroker`: `"tsx"` → `setEnv("tsx")`, `#envSeg` hidden for `"vest"` and `"tsx"`, note text `"A TopstepX login lists every account under it. Nothing trades until you assign it to a strategy."`; step 2 heading `Log in to TopstepX`; `doConnect` sends `broker: "tsx"` and `code` when shown; `needs_code` → show `#cCodeRow`, focus it, toast `"TopstepX sent you a code — type it in"`; the code is cleared in `closeConnect`)
- Test: `tests/test_topstepx_wizard.py` (static text checks, the `tests/test_vest_wizard.py` pattern)

- [ ] **Step 1: Write the failing tests:** `test_step_1_offers_topstepx`, `test_the_env_switch_is_hidden_for_tsx`, `test_doConnect_sends_broker_tsx_and_the_code`, `test_the_password_and_code_are_cleared_on_close`.
- [ ] **Step 2: Run** `pytest tests/test_topstepx_wizard.py -q` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_topstepx_wizard.py tests/test_vest_wizard.py -q` → PASS; then `node --test tests/js/` if present for book.js.
- [ ] **Step 5: Commit** `git commit -m "desk: the TopstepX option in the add-account wizard"`.

### Task 8: Whole-branch check, then the owner's first look

- [ ] **Step 1: Run** `pytest tests -q -x` → all pass (note any failure that also fails on `main`).
- [ ] **Step 2: Whole-branch review** by a fresh reviewer against the spec and this plan.
- [ ] **Step 3: Owner, read only:** start the Mac desk from this worktree, the owner adds his login in the wizard and ticks a combine account; check the card shows the balance and position and the journal has `broker_connected`. No strategy booked.
- [ ] **Step 4: First order, only on the owner's word with him watching:** one MNQ limit bracket far from price on the combine, then cancel it; check the stop and target show at TopstepX.
- [ ] **Step 5: Merge to `main` only when the owner says so.**
