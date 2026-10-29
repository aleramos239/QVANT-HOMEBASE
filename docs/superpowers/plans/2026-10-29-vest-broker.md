# Vest Markets connection (NQ-PERP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Vest account (primary, Vest Capital demo, funded) can be added on the desk through the same wizard as Tradovate and booked to any strategy, trading NQ-PERP through Vest's REST API.

**Architecture:** `vest_auth.py` holds the session: the owner's wallet signs Vest's login message once in the desk dialog, Homebase registers its own P-256 device key, then refreshes and mints per-account tokens by itself (`httpx`). `vest.py` is a `BrokerAdapter`: limit/market entries go straight to Vest with SL/TP attached; stop entries are held in memory (`vest_held.py`) and fired as market orders when the CME price from `MarketFeed` trades the level, behind a loss-floor guard and a slippage cap. `desk_app/brokers.py`, `routes/accounts.py` and the wizard learn the `vest:` login key.

**Tech Stack:** Python 3.14, `httpx`, `websockets` (both present), new `cryptography` (P-256 ECDSA); plain JS in `homebase/static`; pytest via `.venv/bin/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-10-29-vest-broker-design.md` (read it first). Auth facts: vault finding `~/Obsidian/Vault/50-Permanent/Findings/2026-10-29-vest-markets-web-auth-wallet-login-python-reproducible.md`.

## Global Constraints

- Branch `feat/vest` only, in the worktree `.worktrees/vest` (created from main 2a3f3c00; the shared checkout is used by other sessions). **Never commit to `main`** (every commit on main ships to the live VPS). Never hand-copy to the VPS without the owner's OK.
- `git add` only this plan's own paths. The working tree holds unrelated modified/untracked files (`homebase/labrun/host.py`, `tests/test_labrun_*`, `research/...`): never stage them.
- No signature, refresh token, access token or device private key in logs, the journal, exceptions' text, `repr()`, or git. Store them only through `homebase/store/secrets_store.py` under key `vest:<wallet address lowercase>`.
- Homebase never holds or asks for the wallet's private key. The owner signs in his own wallet.
- REST base `https://api-gateway.hz.vestmarkets.com`; account websocket `wss://ws.hz.vestmarkets.com/ws`; API symbol `NDX-USD-PERP` (shown as NQ-PERP; spike); chainId `8453`; networkType as the site sends it (spike confirms the value).
- Sizing: contracts in Homebase; `NQ` ×20 units, `MNQ` ×2 units; both map to `NQ-PERP`. 1 unit = $1 per point.
- Device signature: base64url (no `=`) of ECDSA P-256 / SHA-256 over `"vest-refresh-v1:" + refreshTokenId`, **raw r‖s (64 bytes), not DER**. `devicePublicKey`: base64url (no `=`) of the SPKI DER.
- Request rate: login/refresh go through `homebase/broker/login_budget.py` with the `vest:` key; no broker call from a page refresh; status reads come from caches.
- A held stop entry fires only while the CME feed and the Vest session are both up; otherwise it is skipped and journaled, never entered late. Slippage cap default: skip when NQ-PERP is more than **half the stop distance** past the level (per account, settable).
- Loss-floor guard fails closed: no readable or configured floors → every entry refused.
- Never delete-then-recreate a TP/SL on an open position.
- Vest demo account first; the funded account is booked only on the owner's word.

## Review Focus

- **`md_source` picking a `vest:` login** for market data when no Tradovate token is up: it would try a Tradovate login with a Vest key. Expect: Vest entries are never a market-data source. Test in Task 4.
- **Both held entries crossing in one push** (a fast bar trades both the buy and the sell level): expect only the first in price order to fire, the other dropped, never two positions. Test in Task 3.
- **401 on an order call**: the order was refused, not executed, so mint a fresh account token and resend **once**; any other error or a timeout is never resent (a resent order could double). Test in Task 2.
- **The engine's `_move_brackets` calling `modify_order`** after a Vest fill: expect a clean "not supported" result that leaves the position's SL/TP at Vest untouched, never a cancel. Test in Task 2.
- **The 30-day session running out mid-day**: expect the adapter to report "needs a new wallet signature", held entries skipped and journaled, open positions untouched (their SL/TP live at Vest). Test in Task 1 and Task 3.

---

### Task 0: Spike with the owner (throwaway, Mac, demo account)

Not committed. Lives in a `mktemp -d` folder. Answers the spec's five Phase 0 questions; write each answer back into the spec's "What we know" section and commit the spec alone.

**Files:**
- Create (throwaway): `$TMP/vest_spike.py`, `$TMP/sign.html`

- [ ] **Step 1:** `.venv/bin/pip install cryptography` and add `cryptography` to `requirements.txt` (pinned to the installed version).
- [ ] **Step 2:** Write `vest_spike.py`: a localhost-only HTTP server on `127.0.0.1:8765` that serves `sign.html`, proxies `POST /v3/auth/challenge` (random `signingAddr`, `expiryTime = now + 24h` in ms, `primaryAddr` = the wallet address the page sends), then takes the signature the page posts back and calls `POST /v3/auth/register` with `{networkType, signingAddr, primaryAddr, signature, expiryTime, challengeId, chainId: 8453, rememberMe: true, devicePublicKey}` (no `privyAccessToken`). `sign.html` calls `window.ethereum.request({method:"eth_requestAccounts"})` then `eth_signTypedData_v4` with the challenge's `message` JSON. Print only: HTTP status, `userId`, `accountId`, expiry fields, `isFunded`. Never print tokens.
- [ ] **Step 3:** The owner opens `http://127.0.0.1:8765` in the browser with his wallet and approves. Record: register accepted without a Privy token? (question 1)
- [ ] **Step 4:** With the user token: `GET /v3/accounts?active=true&limit=500`, `GET /v3/capital/accounts`, `GET /v3/capital/limits`, `GET /v3/exchangeInfo`, `GET /v3/ticker/latest`; for the demo account `POST /v3/auth/account-token {accountId}` then `GET /v3/positions/opened`. Record field names (not values of secrets): account ids/kinds, which flag marks demo vs funded, equity field, floor fields, `sizeDecimals`/`priceDecimals` of NQ-PERP, ticker price field, how the per-account call carries `accountId` (header or query). (questions 3, 4)
- [ ] **Step 5:** `POST /v3/auth/refresh {refreshToken, requestId: uuid4, deviceSignature}` once now; save the session with `secrets_store.set_credentials("vest:spike", ...)`; re-run the refresh the next day and compare `refreshExpiresAtMs`. (question 2)
- [ ] **Step 6:** The owner places one demo market order with TP and SL on the site and closes it by hand; the spike then reads `/v3/positions/opened`, `/v3/positions/opened-orders`, `/v3/executions`, `/v3/trades` and listens to the account websocket for 2 minutes during it. Record fill fields, TP/SL order fields, and whether the site has a TP/SL **modify** (in-place) or only delete + create. (question 3)
- [ ] **Step 7:** Question 5 (VPS IP) runs last, only with the owner's OK to copy one script to the VPS.
- [ ] **Step 8:** If question 1 or 5 fails, stop and bring it to the owner. Otherwise commit the updated spec and `requirements.txt`:

```bash
git add docs/superpowers/specs/2026-10-29-vest-broker-design.md docs/superpowers/plans/2026-10-29-vest-broker.md requirements.txt
git commit -m "vest: design + plan, spike answers, cryptography dependency"
```

Every later task uses the field names Task 0 recorded. Where this plan names a field, the spike's answer wins.

---

### Task 1: Vest session (`vest_auth.py`)

**Files:**
- Create: `homebase/broker/vest_auth.py`
- Test: `tests/test_vest_auth.py`

**Interfaces:**
- Produces:
  - `class DeviceKey`: `new() -> DeviceKey`, `from_pem(pem: str) -> DeviceKey`, `pem() -> str`, `public_b64() -> str`, `sign_refresh(refresh_token_id: str) -> str`
  - `class NeedsSignature(RuntimeError)`: raised when no valid refresh token is left
  - `class VestSession(key: str, *, http: httpx.AsyncClient | None = None, budget: LoginBudget | None = None)`:
    - `async challenge(primary_addr: str) -> dict` → `{"challengeId", "message", "signingAddr", "expiryTime"}` (kept in memory for `register`)
    - `async register(primary_addr: str, signature: str) -> dict` → user session; stores `{primary_addr, refresh_token, refresh_token_id, refresh_expires_ms, device_pem}` under `self.key`
    - `async user_token() -> str` (refreshes when under 60 s left)
    - `async account_token(account_id: str) -> str` (mints via `/v3/auth/account-token` when under 60 s left; cached per account)
    - `async request(method: str, path: str, *, account_id: str | None = None, **kw) -> httpx.Response`: adds the right Bearer; on **401** mints a fresh token and resends **once**
    - `refresh_expires_ms: int`, `needs_signature: bool`, `__repr__` shows only the key and expiries

- [ ] **Step 1: Write the failing tests** (httpx `MockTransport`, `run()` helper as in `tests/conftest.py`):
  - `test_device_signature_verifies`: `k = DeviceKey.new()`; decode `k.public_b64()` (SPKI) and `k.sign_refresh("rt1")` (64 bytes raw); verify with `cryptography` over `b"vest-refresh-v1:rt1"`. `DeviceKey.from_pem(k.pem()).public_b64() == k.public_b64()`.
  - `test_register_body_and_store`: mock challenge + register; assert register body has `devicePublicKey`, `rememberMe is True`, no `privyAccessToken`; `secrets_store.get_credentials("vest:0xabc")` has `refresh_token`, `device_pem`; `repr(session)` contains neither.
  - `test_refresh_body`: an expired user token → one `POST /v3/auth/refresh` with `refreshToken`, a uuid `requestId`, `deviceSignature` that verifies; new expiry stored.
  - `test_refresh_rejected_needs_signature`: refresh answers 401 → `NeedsSignature` raised, `session.needs_signature is True`, no second refresh within the budget's backoff.
  - `test_401_resend_once`: an account call answers 401 then 200 → exactly one mint and one resend; 401 twice → raises, no third call.
  - `test_no_resend_on_timeout_or_500`: `httpx.ReadTimeout` / 500 → raised as is, the call made exactly once.
  - `test_secrets_never_logged`: run register + refresh with `caplog` at DEBUG; no token, signature or PEM text in `caplog.text`.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_vest_auth.py -v` → FAIL (module missing).
- [ ] **Step 3:** Implement `homebase/broker/vest_auth.py`. `DeviceKey` uses `cryptography` `ec.SECP256R1`; raw signature from `decode_dss_signature` → `r.to_bytes(32)+s.to_bytes(32)`. Refresh and login count against `login_budget` under `self.key` (`blocked`/`record_login`/`login_result`), like Tradovate's.
- [ ] **Step 4:** Run the tests → PASS.
- [ ] **Step 5: Commit**

```bash
git add homebase/broker/vest_auth.py tests/test_vest_auth.py
git commit -m "vest: session (wallet-signed login, own device key, refresh, account tokens)"
```

---

### Task 2: Vest adapter core (`vest.py`)

**Files:**
- Create: `homebase/broker/vest.py`
- Test: `tests/test_vest_adapter.py`

**Interfaces:**
- Consumes: `VestSession` (Task 1); `BrokerAdapter`, `OrderRequest`, `OrderResult`, `FillEvent` from `homebase/broker/base.py`.
- Produces:
  - `units_of(symbol: str, qty: int) -> str` (NQ ×20, MNQ ×2, formatted with NQ-PERP's `sizeDecimals`; any other root raises `ValueError`)
  - `class VestAdapter(BrokerAdapter)(account_id: str, *, keyring_key: str, vest_account_id: str, session: VestSession | None = None, floors: dict | None = None, slip_frac: float = 0.5)`
  - `list_accounts() -> list[dict]` rows `{"name", "id", "kind": "primary"|"demo"|"funded", "demo": bool}` (wizard step 3)
  - `async perp_price() -> float` (`/v3/ticker/latest`, NQ-PERP)
  - `place_order`, `place_bracket` (Market/Limit only here; Stop/StopLimit → Task 3), `cancel_order_by_id`, `flatten_symbol`, `flatten_all`, `cancel_all`, `get_net_position` (contracts, units ÷ 20 for NQ), `get_balance`, `observe_fills`
  - `modify_order(...)` returns `OrderResult(ok=False, error="vest: modify not supported")` and never cancels anything. If the spike found an in-place TP/SL modify, it instead moves the SL/TP in place (spec: re-centre on the fill), with a test that the call is that one modify and nothing else

- [ ] **Step 1: Write the failing tests** (fake `VestSession` recording calls, pattern of `tests/test_order_bodies_pinned.py`):
  - `test_units_of`: `units_of("NQZ6", 1) == "20"`, `units_of("MNQZ6", 3) == "6"`, `units_of("ESZ6", 1)` raises.
  - `test_limit_bracket_body`: Buy Limit 1 NQ at 21000, SL 20980, TP 21040 with NQ-PERP at 21030 (CME 21010) → one `POST /v3/positions/open` body `{symbol:"NQ-PERP", side:"LONG", orderType:"LIMIT", quantity:"20", ...}`, SL/TP keep the point distances (-20/+40) from the limit price; `accountId` sent the way the spike recorded.
  - `test_market_bracket_body`: Sell Market 2 MNQ, SL +15 pts, TP -30 pts → `side:"SHORT"`, `quantity:"4"`, SL/TP from `perp_price()`.
  - `test_modify_never_cancels`: `modify_order` → `ok=False`; the fake session saw no DELETE and no POST.
  - `test_401_order_resent_once` and `test_timeout_order_not_resent` (via the session behaviour of Task 1, asserted at adapter level: exactly 2 / exactly 1 open calls).
  - `test_flatten_all_closes_and_cancels`: one open position + one resting order → `/v3/positions/close` and `/v3/positions/cancel-order` once each.
  - `test_fill_event`: a fake websocket (or read) message for a fill → `on_fill` gets a `FillEvent` with contracts (units ÷ 20) and the fill price.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_vest_adapter.py -v` → FAIL.
- [ ] **Step 3:** Implement `homebase/broker/vest.py`. Fills: the account websocket if the spike saw fill messages on it; else read `/v3/positions/opened` + `/v3/executions` every 2 s only while an order rests or a position is open, never otherwise.
- [ ] **Step 4:** Run the tests → PASS.
- [ ] **Step 5: Commit**

```bash
git add homebase/broker/vest.py tests/test_vest_adapter.py
git commit -m "vest: adapter for limit/market entries with SL/TP, sizing, flatten, fills"
```

---

### Task 3: Held stop entries, loss-floor guard, slippage cap (`vest_held.py`)

**Files:**
- Create: `homebase/broker/vest_held.py`
- Modify: `homebase/broker/vest.py` (`place_bracket` for Stop/StopLimit, `cancel_order_by_id` for held ids, `on_bar`)
- Test: `tests/test_vest_held.py`

**Interfaces:**
- Produces:
  - `@dataclass HeldEntry(id: str, symbol: str, side: str, qty: int, level: float, sl_pts: float, tp_pts: float | None, day: str, oco_group: str | None)`
  - `class HeldBook(path: Path)`: `add(e)`, `drop(id)`, `drop_group(group)`, `crossed(root: str, bar: Bar) -> list[HeldEntry]` (in price order, at most one per `oco_group`), `restore(today: str, last_price: float) -> list[HeldEntry]` (only today's entries whose level price has not reached)
  - `floor_room(equity: float, floors: dict, open_risk: float) -> float | None` (`None` = no floors → refuse)
  - `slip_ok(level: float, perp_price: float, side: str, sl_pts: float, slip_frac: float) -> bool`
  - `VestAdapter.on_bar(root: str, bar: Bar) -> None` (called by the feed hook, Task 4)
- Trigger rule: a held Buy fires when a push's bar high rises to ≥ level (a higher high than the last push of the same bar, or a new bar's high); Sell mirrored on the low. The `level` is CME; the SL/TP are point distances from NQ-PERP's price at fire time.
- Held ids are returned as `OrderResult.order_id` like a resting order, so the engine's cancel path drops them. The two legs of a two-sided entry share `oco_group` (the engine's legs for one signal).

- [ ] **Step 1: Write the failing tests:**
  - `test_buy_fires_once_on_cross`: hold Buy Stop 21000; push high 20995 → nothing; push high 21001 → one market `open` with SL/TP; next push → nothing.
  - `test_two_sided_one_push_only_first`: Buy 21000 and Sell 20950 in one `oco_group`; one push with high 21001 and low 20949 (open 20990) → exactly one `open`, the other dropped and journaled.
  - `test_skip_when_feed_or_session_down`: session `needs_signature` (or feed status down) when the level trades → no `open`, entry dropped, journal `vest_held_skipped` with the reason; the level trading again later fires nothing.
  - `test_slippage_cap`: SL 20 pts, NQ-PERP 11 pts past the level → skipped (`slip_frac` 0.5); 9 pts → fires.
  - `test_floor_guard`: equity 50,000, max-drawdown floor 48,000, open risk 1,500, new entry 1 NQ × 30 pts = 600 → refused; 1 MNQ × 30 pts = 60 → allowed. With a daily loss limit, the daily floor is day-start equity − limit, and the **higher** of the two floors is used. No floors from API or config → refused.
  - `test_daily_floor_resets_2000_et`: day-start equity is the API's if it has one, else recorded by the adapter at the first read after 20:00 ET and saved in the held-book file; an account with a daily limit and no day-start equity → refused.
  - `test_restore_after_restart`: saved entries for today; `restore(today, last_price)` keeps a Buy at 21000 with last 20990, drops it with last 21002, drops yesterday's.
  - `test_cancel_drops_held`: `cancel_order_by_id(held_id)` → removed, no broker call.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_vest_held.py -v` → FAIL.
- [ ] **Step 3:** Implement `vest_held.py` and wire it into `vest.py`. `HeldBook` file (the spec's "saved with the day's state"): `homebase/.state/vest_held_<account_id>.json`, written with `homebase/core` `write_json`. Floors come from the spike's API fields, else `AccountCfg.floors` (Task 4). The guard runs at place time (limit/market) and again at fire time (held).
- [ ] **Step 4:** Run the tests → PASS.
- [ ] **Step 5: Commit**

```bash
git add homebase/broker/vest_held.py homebase/broker/vest.py tests/test_vest_held.py
git commit -m "vest: held stop entries on CME price, loss-floor guard, slippage cap"
```

---

### Task 4: Desk wiring (`brokers.py`, `config.py`, `feed.py`)

**Files:**
- Modify: `homebase/desk_app/brokers.py` (`_key_env`, `md_source`, `build_adapter`, `make` reconnect loop)
- Modify: `homebase/config.py` (`AccountCfg`)
- Modify: `homebase/data/feed.py` (`MarketFeed._take`)
- Test: `tests/test_vest_wiring.py`

**Interfaces:**
- Consumes: `VestAdapter` (Tasks 2-3).
- Produces:
  - `AccountCfg.vest_account_id: str = ""`, `AccountCfg.floors: dict = field(default_factory=dict)` (`{"max_drawdown_equity": float, "daily_loss": float}`, hand-set only when the API has none), `AccountCfg.slip_frac: float = 0.5`
  - `is_vest_key(key: str) -> bool` in `brokers.py` (`key.startswith("vest:")`)
  - `MarketFeed.bar_listeners: list[Callable[[str, Bar], None]]`, called from `_take` for every pushed bar; a listener's exception is caught and logged, never breaks the feed

- [ ] **Step 1: Write the failing tests:**
  - `test_build_adapter_vest`: `AccountCfg(keyring_key="vest:0xabc", vest_account_id="123")` → a `VestAdapter`; a `tv:` key → `TradovateAdapter` as before.
  - `test_md_source_skips_vest`: only Vest entries configured → `md_source` raises "no accounts configured for market data"; a Vest entry plus a Tradovate entry → the Tradovate key.
  - `test_key_env_vest`: `_key_env("vest:0xabc") == "vest"`; `tv:` keys unchanged. (A Vest entry's `live` comes from its row's `demo` flag, Task 5.)
  - `test_bar_listener_called_and_isolated`: a listener raising does not stop a second listener or the bar update.
  - `test_needs_signature_status`: a Vest adapter whose session raises `NeedsSignature` on connect → `acct_status[aid]["error"] == "needs a new wallet signature"`, and the reconnect loop does not retry it until the login is signed again.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_vest_wiring.py -v` → FAIL.
- [ ] **Step 3:** Implement. In `make`, after the feed exists, append each `VestAdapter.on_bar` to `feed.bar_listeners` (and on adapter rebuild). Vest entries never feed `_md_token_of`.
- [ ] **Step 4:** Run the new tests, then the whole suite: `.venv/bin/python -m pytest tests -q` → no new failures against `main`'s baseline (run the baseline first and note any already-failing tests).
- [ ] **Step 5: Commit**

```bash
git add homebase/desk_app/brokers.py homebase/config.py homebase/data/feed.py tests/test_vest_wiring.py
git commit -m "vest: desk wiring (build_adapter, md_source skips vest, bar listeners, needs-signature status)"
```

---

### Task 5: Routes (`/api/vest/challenge`, `/api/connect` Vest branch, add-many)

**Files:**
- Modify: `homebase/routes/accounts.py` (`connect`, `accounts_add_many`, `logins`)
- Test: `tests/test_vest_routes.py`

**Interfaces:**
- Consumes: `VestSession.challenge/register` (Task 1), `VestAdapter.list_accounts` (Task 2), `is_vest_key` (Task 4).
- Produces:
  - `POST /api/vest/challenge {address}` → `{"ok": true, "typed_data": <message JSON>}` (session kept in memory for 5 minutes per address)
  - `POST /api/connect {broker: "vest", address, signature}` or `{saved_key: "vest:..."}` → same shape as Tradovate: `{"ok", "key", "env": "vest", "accounts": [...]}`; a saved key whose session needs a signature answers `{"ok": false, "error": "needs a new wallet signature", "key"}`
  - `/api/logins` rows for `vest:` keys: `label` = short address `0xBBE1…1EAB`, `env` = `"vest"`
  - `add-many` for a `vest:` key: each entry gets `vest_account_id` from the row and `live = not row["demo"]`

- [ ] **Step 1: Write the failing tests** (FastAPI `TestClient` as other route tests do; fake session):
  - `test_challenge_then_connect_lists_accounts`: challenge → connect with a signature → 3 rows (primary, demo, funded); `secrets_store` has `vest:0xabc`.
  - `test_connect_saved_vest_key`, `test_connect_saved_needs_signature`.
  - `test_add_many_vest_live_flag`: adding the demo row → `live False`; the funded row → `live True`; both carry `vest_account_id`.
  - `test_challenge_rejects_bad_address`: not `0x` + 40 hex → 400.
  - `test_no_signature_in_journal`: after connect, the engine journal text holds no signature.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest tests/test_vest_routes.py -v` → FAIL.
- [ ] **Step 3:** Implement in `homebase/routes/accounts.py`; the Vest branch uses the same `budget.blocked` / `record_login` / `login_result` calls as the Tradovate branch.
- [ ] **Step 4:** Run the tests → PASS.
- [ ] **Step 5: Commit**

```bash
git add homebase/routes/accounts.py tests/test_vest_routes.py
git commit -m "vest: connect routes (wallet challenge, signed login, add accounts)"
```

---

### Task 6: Wizard (Vest option, Connect wallet)

**Files:**
- Modify: `homebase/static/index.html` (`#wstep1` new `#optVest`; `#wstep2` Vest variant), `homebase/static/desk/book.js` (`WIZ.broker`, `doConnect`, `loadLogins`), bump the `?v=` cache tag the page uses

**Interfaces:**
- Consumes: the Task 5 routes.

- [ ] **Step 1:** Step 1 gets **Vest** ("Your wallet signs in") beside Tradovate; picking it hides the Demo/Live switch (a Vest login lists demo and funded together).
- [ ] **Step 2:** Step 2 for Vest: saved Vest logins (same list, `env === "vest"`) and two buttons, **Coinbase Wallet** (first) and **Browser wallet**. Coinbase: `createCoinbaseWalletSDK({appName:"Homebase", appChainIds:[8453], preference:{options:"all"}}).getProvider()` from `@coinbase/wallet-sdk@4.3.7`, vendored as one file `homebase/static/vendor/coinbase-wallet-sdk-4.3.7.js` (esm.sh `?bundle` build; no remote imports left in it). Browser wallet: EIP-6963 discovery, else `window.ethereum`. Two clicks, because Safari blocks a second pop-up not started by a click: **1. Connect** (`eth_requestAccounts` → `POST /api/vest/challenge`) then **2. Sign** (`eth_signTypedData_v4(address, typed_data)` → `POST /api/connect {broker:"vest", address, signature}`) → step 3 as today. The spike page `.superpowers/sdd/2026-10-29-vest-broker/spike/vest_spike.py (git-ignored workspace)` (PAGE) is the working reference — the owner signed with it on 2026-10-29. The signature is never kept in a variable past the POST.
- [ ] **Step 3:** Step 3 rows show the kind (Demo / Funded / Primary); the funded row is never pre-ticked.
- [ ] **Step 4:** Check in the app (skill `run`) on the Mac with the owner: the wizard adds the Vest demo account; a page refresh makes no Vest call (browser network tab of the desk: none to `vestmarkets.com`).
- [ ] **Step 5: Commit**

```bash
git add homebase/static/index.html homebase/static/desk/book.js homebase/static/vendor/coinbase-wallet-sdk-4.3.7.js
git commit -m "vest: wizard option and wallet sign-in"
```

---

### Task 7: Demo run with the owner, then hand back

- [ ] **Step 0:** Waits for the owner's Vest Capital purchase (spike: he has none yet; the free demo is disabled for him). On the first day, capture the order/fill/TP-SL fields and the loss-floor fields (spec Phase 0, questions 3 and 4) and fix the adapter where they differ.
- [ ] **Step 1:** On the Mac desk, book the **Vest** account to one strategy the owner names, in a session where its stop level trades. Watch: held entry → fire → position at Vest with SL and TP → exit. Journal shows the slippage between level and fill.
- [ ] **Step 2:** Leave it a full day: the session refreshes by itself; no repeated logins in the journal.
- [ ] **Step 3:** Ask the owner for the VPS check (spec Phase 0, question 5) if not done in Task 0, then for the merge to `main`. Do not merge without his word.
