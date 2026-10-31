# AlphaTrader (Alpha Futures) connection — design

Date: 2026-10-30. Branch: `feat/alphatrader` (worktree `.worktrees/alphatrader`). Status: draft, for the owner's approval.

## Intent

The owner wants to connect **Alpha Futures** accounts to Homebase, the way TopstepX, Tradovate and Vest are connected
("now lets add alpha trader", 2026-10-30). Alpha Futures accounts trade on **AlphaTrader**, Alpha's own web and mobile
platform. This project builds the **connection** only: an AlphaTrader account sits on the desk like a TopstepX account, and
a strategy can be booked on it later.

Like the others it works **without an API key**: Homebase logs in the way the AlphaTrader website does, with the owner's
Alpha **email and password** (owner, 2026-10-30: "email and password"; not "Sign in with Google").

**The rules risk, accepted by the owner.** Alpha's help center bans "AI/software advantages" and copy/signal trading;
reviews say fully automated bots are banned (semi-automated with the trader watching is allowed); Alpha's homepage
advertises "automated trading". The Desk is fully automated. The owner accepts that Alpha may refuse payouts or close
accounts (owner, 2026-10-30: "i accept that they may refuse payouts"). This reverses the TopstepX spec's "Alpha Futures is
out" line. Rules reference: `~/Obsidian/Vault/50-Permanent/Findings/2026-10-30-alpha-futures-funded-account-rules.md`.

**No account yet** (owner, 2026-10-30: "i havent bought the accounts yet"). Alpha fixes the platform at purchase, so the
owner must pick **AlphaTrader** when he buys. Until then, everything is built and tested offline; the read-only check runs
once he has an account.

## What we know about AlphaTrader (read from the live site's code, 2026-10-30)

From `https://futures.alphatrader.com/signin` and its bundle `static/js/main.2fcc5e96.js`:

- **Alpha's server** `https://apiv2.alphatrader.com`:
  - Login: `POST /api/v1/auth/login/` (JSON body; field names to confirm) → `data.tokens` (access token, refresh token,
    `id_token`). Renew: `POST /api/v1/auth/token/refresh/ {refresh_token}`. Profile: `GET /api/v1/auth/me/`.
  - A one-time code step exists (routes `/verify-mfa`, `/mfa-required`; MFA calls under
    `https://api-futures.alphatrader.com/api/auth/mfa/...`). Whether the owner's login asks for a code is checked by the spike.
  - A EULA must be signed once on the site (`eula_signed`); Homebase does not sign it.
  - T4 login: `POST /api/v1/t4/credentials/token/` → `data.signed_credential_token`, a JWT signed with a public key in the
    bundle. Its payload carries `t4_firm`, `t4_username`, `t4_password`, `t4_app_name`, `t4_app_license`.
  - Also present: `/api/v1/t4/accounts/`, `/api/v1/t4/orders/`, `/api/v1/t4/trading/cancel-all/` (shapes unknown).
- **CTS T4** (the trading engine under AlphaTrader): websocket `wss://wss-sim.t4login.com/v1` (all Alpha accounts are
  simulated), REST `https://api-sim.t4login.com`. Messages are **protobuf** (`t4proto.v1`): `ClientMessage` /
  `ServerMessage` wrapping `LoginRequest {firm, username, password, appName, appLicense, priceFormat}` → `LoginResponse`,
  `Heartbeat`, `AccountSubscribe` (all accounts, all updates) → `AccountSnapshot` / `AccountUpdate` / `AccountPosition` /
  `AccountProfit`, `OrderSubmit` / `OrderRevise` / `OrderPull` → `OrderUpdate*` (status NONE, HELD, WORKING, FINISHED,
  REJECTED; trades in `OrderUpdateTrade`). Order prices: `PRICE_TYPE_MARKET`, `LIMIT`, `STOP_MARKET`, `STOP_LIMIT`.
  **Brackets:** `OrderLink` `AUTO_OCO` (T4's attached stop + target). Login results include `LOGGED_IN_ELSEWHERE` and
  `TWO_FACTOR_REQUIRED`.
- **One session at a time:** the site logs out with "logged_in_elsewhere", like TopstepX.

Not known yet (the spike checks, read-only): the login body's field names and answer, whether a code is asked, the token
lifetimes, the protobuf field numbers Homebase needs (read from the bundle's encoder), account ids and names, contract ids
for NQ / MNQ / ES / MES / GC / MGC, how an AUTO_OCO bracket is sent and how its legs report, the position sign.

## Goals

1. An AlphaTrader adapter (`homebase/broker/alphatrader*.py`) implementing `BrokerAdapter`, built by `build_adapter` in
   `homebase/desk_app/brokers.py` for an account whose login key starts `atr:`. Model: the TopstepX adapter
   (`homebase/broker/topstepx*.py`), its session, kick handler, caches and tests.
2. **Login like TopstepX:** email + password, checked by a real login, stored in `secrets_store` under `atr:<email>` (never
   in git, logs or the journal). Homebase renews the token itself; when it cannot, it logs in again with the saved password
   through the login budget. A code box in the wizard only if Alpha asks for one; a re-login that needs a code stops that
   login's accounts with "AlphaTrader needs a code" until the owner enters it.
3. **The same desk wizard:** an **AlphaTrader** tile beside TopstepX; log in; tick accounts; saved login listed, reusable,
   deletable; reconnect / remove through the login budget.
4. **Orders:** market, limit, stop and stop-limit entries, with the strategy's stop loss and take profit attached at T4
   (AUTO_OCO), so a position is protected the moment it fills. Flatten, cancel-all, cancel by id, net position and balance
   as the desk needs them.
5. **Fills** from the T4 socket (`OrderUpdateTrade`, positions) into `observe_fills`, the same `FillEvent` shape.
6. **Kicked out: always take it back** (as TopstepX, owner's rule 2026-10-30), through the login budget so it can never
   become a login flood. Each kick journaled and counted on the card.
7. **Low request rate:** one Alpha login and one T4 socket per login, shared by its accounts; status reads from caches.
8. **Booking refused at first** (`ATR_BOOKING_OPEN = False`), exactly like TopstepX, until the spike has confirmed the
   guessed shapes and the owner lifts it.

## Calls made by the designer (the owner may overrule)

- **No new package.** Python's `protobuf` is not installed (a new package must be installed on the server by hand). A small
  hand-written protobuf encoder/decoder for the handful of messages above (varints and length-delimited fields) is enough.
- **Market data:** an AlphaTrader login is never a market-data source (`md_source` skips it, as it skips TopstepX and Vest).
- **Forced closes:** Alpha's own closes (Friday close, rule breaches) reach Homebase as outside fills, handled as today.
- **Live vs practice:** every Alpha account is simulated; the card shows Alpha's own account name and status.
- **The spike** is read-only (login, T4 login, accounts, positions, the socket for 60 s) and the owner types his own password.
  The first real order goes only on the owner's word, with him watching.

## Non-goals

- "Sign in with Google", the Alpha dashboard, buying accounts, signing the EULA.
- T4 market data or charts; the CTS T4 paid API; Tradesea / WealthCharts / TradingView accounts at Alpha.
- Alpha's prop rule set for the prop sim (a separate job).

## Anti-goals: failure even if it "works"

- A missed fill or a doubled order breaks Alpha's daily loss limit.
- A position without its stop at T4, even briefly.
- A login loop that hammers Alpha or T4.
- The password, the Alpha tokens or the decoded T4 password in logs, the journal, errors, HTTP answers, the page or git.
- Anything reaching `main` (and so the Chicago server) before the owner says so.

## Constraints

- The live desk runs on the Chicago VPS; Python with `httpx` and `websockets`. JWT payload decoding needs no package
  (base64 + json; the signature need not be checked to read Homebase's own credentials).
- Follow the TopstepX patterns and lessons (`~/Obsidian/Vault/50-Permanent/Findings/2026-10-30-topstepx-broker-build-lessons.md`):
  one login lock shared by renewal, kick handler and wizard; unknown is never flat; engine safety checks need order status
  and bracket ids; flatten closes then cancels only what closed.
- Tests never reach Alpha or T4 (an autouse guard like `tests/test_topstepx*`).

## Builder questions, settled (2026-10-30)

A builder read this design first. Each answer is marked: **(project)** follows from the TopstepX code already on main, and
**(designer's call)** is the owner's to overrule.

1. **Is the bracket attached in the same message as the entry?** Unknown until the spike. **(designer's call)** Send the
   entry with AUTO_OCO legs. Also copy TopstepX's no-stop guard: a position with no working stop seen after a short grace
   period is journaled and flagged on the card. An `ATR_FLATTEN_IF_NO_STOP` switch closes that position; it starts off, like
   `TSX_FLATTEN_IF_NO_STOP`. Booking stays refused until the spike shows how the legs are sent and reported. Stop-limit
   entries may carry a bracket only if the spike shows T4 accepts that. Bracket child ids are tracked from `OrderUpdate*`
   as `sl_order_id` / `tp_order_id`.
2. **Where do the protobuf field numbers come from?** **(project)** A saved copy of the bundle is at
   `.spike/alphatrader-main.2fcc5e96.js` in this worktree. `.spike/` is git-excluded and never committed. The builder may
   also fetch the bundle again, read-only; it is a public file. Without an account, "done" means:
   - the codec's encode/decode round-trip tests pass;
   - each message's field numbers carry a code comment pointing to where the bundle defines them;
   - adapter tests run against a fake T4 socket.
3. **Which login is "the session"?** **(designer's call)** The login budget counts every Alpha **password** login and
   every **T4 socket** login. An Alpha token refresh and a credential-token fetch cost nothing. A T4 reconnect fetches a
   fresh `signed_credential_token` first, refreshing the Alpha token if needed, and then counts one budget slot. The kick
   handler watches the T4 socket (`LOGGED_IN_ELSEWHERE`, or the socket closing) and Alpha 401s. One login lock covers all
   three layers. The spike checks which layer the website's login actually kicks.
4. **What is `live` for an Alpha account?** **(project)** Same rule as TopstepX (`routes/accounts.py`): an account Alpha
   marks as practice or evaluation is demo (`live=False`); every other account, funded or unmarked, is `live=True`, the
   stricter rules. The spike confirms which field carries the mark.
5. **Contract and roll.** **(project)** Same as TopstepX `contract_id()`: the root's front month from
   `symbols.front_month`, resolved when the order is placed, so the roll follows the desk's calendar. Flatten also closes an
   older month still held. The spike confirms the T4 contract-id format.
6. **Copy TopstepX, and its parked bugs?** **(designer's call)** Write a separate AlphaTrader copy. It does not share code
   with TopstepX, which is live on main and stays untouched. The copy is written with the 7 parked TopstepX fixes already
   in place (TopstepX spec, "Before booking opens"):
   - a refused close on one month still cancels the other month's orders;
   - re-close only on a sign flip;
   - flatten reads positions first;
   - the no-stop flag clears when a late stop arrives;
   - reseed the order cache while it is unknown;
   - no no-stop close while the order cache is unknown;
   - positions are not known while a contract is dirty;
   - the stop check looks at size.

## Left to the builder

- File split (adapter, login/session, T4 socket + codec), the protobuf field map, symbol → T4 contract mapping, how the code
  step fits the wizard (reuse the TopstepX code row).
