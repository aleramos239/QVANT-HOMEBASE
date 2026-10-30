# Vest Markets connection (NQ-PERP) — design

Date: 2026-10-29. Branch: `feat/vest` (worktree `.worktrees/vest`). Status: approved 2026-10-29; login switched to the wallet route the same day.

## Intent

The owner has a **Vest Capital funded account** (next.vestmarkets.com) and wants Homebase to run his strategies on it,
on **NQ-PERP**, the same way they run on Tradovate today. Which strategies is not decided yet; he picks them after
testing. So this project builds the **connection** only: a Vest account that can sit on the desk like a Tradovate or
paper account, and that any strategy can later be booked on.

Like Tradovate (see `homebase/broker/tradovate_auth.py`), it must work **without an official API key**: the owner has
none. He accepted the risk that Vest's prop terms put "third-party tools" at the user's own risk (account suspension or
lost payouts).

## What we know about Vest (read from the live site's code, 2026-10-29)

- **Login** is through Privy (email code, Google, SMS, passkey or a crypto wallet). The owner's funded
  account is on his own wallet (0xBbe1…1eab), which shows its own "Signing with" prompt and can sign on any page.
- After the Privy login, the site makes a throwaway signing address, has the wallet sign an EIP-712 challenge
  (`POST /v3/auth/challenge`, then `POST /v3/auth/register`), and gets an **access token (~15 min)** and a **refresh
  token (30 days with Remember me)**.
- Refreshing (`POST /v3/auth/refresh`) needs a **device signature** from a P-256 key the site makes with WebCrypto as
  **non-extractable** and keeps in IndexedDB. Python cannot copy it out, so the session can only be kept alive inside a
  browser.
- **Orders are plain REST calls** with `Authorization: Bearer <token>` to `https://api-gateway.hz.vestmarkets.com`:
  `/v3/positions/open`, `/close`, `/reduce`, `/append`, plus TP/SL create and delete; reads at `/v3/positions/opened`,
  `/v3/accounts`, `/v3/executions`, `/v3/trades`; an account websocket. Each order carries its own `accountId`, and
  **each account (the funded one included) gets its own access token**. No per-order signature.
- **Order types:** Market (IOC/FOK) and Limit (GTC/IOC/FOK/post-only), each with TP and SL attachable, plus Reduce Only.
  **There are no stop orders for entries.**
- **Sizing:** NQ-PERP trades in units; 1 unit = $1 per point. **1 NQ = 20 units, 1 MNQ = 2 units.** NQ-PERP prices off
  the CME front NQ contract (NQZ6 now), inside a ±0.25% band, with funding paid hourly.
- **Funded-account rules:** max drawdown, and on evaluation accounts an optional daily loss limit that resets at
  **20:00 ET**. Going below either floor **closes the account for good**.
- The site runs FingerprintJS, and checks location (`/api/geo`).
- **Vest Capital has a demo account** (`/v3/capital/demo`).
- No link-a-wallet or export-wallet feature exists, so a separate login-only wallet would open a different, empty
  account. That route was looked at and dropped.
- **New, 2026-10-29 (from the owner's wallet login):** the client supplies the device key itself (`devicePublicKey` in
  `/v3/auth/register`), and the refresh signs `"vest-refresh-v1:" + refreshTokenId` with it. So if the account's
  primary wallet is an **external** wallet (one that shows a "Signing with 0x…" prompt), Homebase can make its own
  device key in Python, have the owner approve one `SignerProof` in his wallet, and keep the session alive with **no
  browser at all**. Details: vault finding `2026-10-29-vest-markets-web-auth-wallet-login-python-reproducible`.
  **Answered: the funded account is on that wallet (owner, 2026-10-29), so this is the route.**

## Goals

1. A Vest broker adapter (`homebase/broker/vest*.py`) implementing `BrokerAdapter` (`homebase/broker/base.py`), built by
   `build_adapter` in `homebase/desk_app/brokers.py` for an account marked as Vest in config.
2. **Login: the owner's wallet signs, Homebase keeps the session (owner, 2026-10-29: the funded account is on his
   wallet 0xBbe1…1eab).** No browser, no Privy. Homebase asks Vest for the login message (`/v3/auth/challenge`), the
   owner approves it in his wallet from the desk dialog, and Homebase registers with **its own P-256 device key**
   (`/v3/auth/register`, rememberMe). It refreshes by itself (`/v3/auth/refresh`, device signature) and mints each
   account's token (`/v3/auth/account-token`). The owner signs again only when the 30-day login runs out. Orders are
   API calls. *(Replaces the hidden browser, which this design first chose.)*
3. **Entries:** limit and market entries go to Vest as they are. **Stop entries are held by Homebase:** it watches the
   live CME NQ price it already has and, the moment a level trades, sends a **market order with the strategy's stop
   loss and take profit attached**. The two-sided entry (buy stop + sell stop) is both held by Homebase; when one fires,
   the other is dropped. If Homebase is down, nothing fires, which leaves the account flat rather than unprotected.
4. Every position has its stop loss at Vest from the moment it opens. Never an unprotected position.
5. **Loss-floor guard:** Homebase reads the account's floors from Vest (max drawdown, and the daily loss limit with its
   20:00 ET reset when the account has one). It refuses a new entry when that entry's full stop-loss risk, added to
   what is already at risk, could take equity below either floor.
6. **Sizing** stays in contracts in Homebase; the adapter converts (NQ ×20, MNQ ×2) and maps `NQ`/`MNQ` to `NQ-PERP`.
7. **Low request rate** from day one, the Tradovate lessons (`docs/superpowers/GOTCHAS.md`; findings 2026-09-16 and
   2026-09-29): a login budget per Vest login with backoff after failures and after 429s; one browser per Vest login;
   status reads from caches, never broker calls on page refresh.
8. **The owner signs himself**, in his own wallet, from the desk dialog. Homebase never sees or stores the wallet's
   key. The refresh token and the device key are stored like a Tradovate password (`secrets_store`, under
   `homebase/.state/`, not in git). No signature, token or key is ever written to logs, the journal or git.
9. **Testing order:** Vest's demo account first. The funded account is booked only when the owner says so.

## Adding and reconnecting: exactly like Tradovate (owner, 2026-10-29)

The owner: "i want it to function exactly like the tradovate login". So a Vest account goes through the **same desk
wizard and the same routes' shape** as Tradovate (`homebase/routes/accounts.py`, the `wstep*` steps in
`homebase/static/index.html`):

| Step | Tradovate today | Vest |
|---|---|---|
| 1. Pick the broker | Tradovate / Paper | adds **Vest** |
| 2. Log in | username + password, verified by a real login (`/api/connect`) | **Connect wallet**: the owner approves Vest's login message in his wallet; verified by a real login (`/api/connect`) |
| Saved login | `secrets_store` key `tv:<env>:<user>`, listed under saved logins, re-usable, deletable | `secrets_store` key `vest:<wallet address>` (refresh token, its id and expiry, the device key); listed, re-usable and deletable the same way |
| 3. Tick accounts | every account under the login | every Vest account under the login: primary, Vest Capital demo, funded |
| Added accounts | `AccountCfg` entries, never booked | the same; a Vest entry is never booked by itself |
| Reconnect / Remove | automatic, through the login budget | the same paths (`desk_app/brokers.py`), the same budget |

The one difference Vest forces: there is **no password**, so nothing can log in again by itself once the 30-day
session ends. The desk then shows the login as needing a new signature, the same place a failed Tradovate login
shows, and the owner signs again in the same dialog.

## Non-goals

- Vest market data on the charts. The charts and the stop-entry trigger keep using CME ticks.
- Choosing or testing strategies (blueprint work, separate).
- Markets other than NQ-PERP (ES-PERP and others can follow later the same way).
- Chart trading on Vest (the adapter may leave the chart-trading methods at their "not supported" defaults).
- Modelling funding or NQ-PERP prices in the backtester.

## Anti-goals: failure even if it "works"

- A Homebase bug, a missed fill or a doubled order breaks a loss floor and closes the funded account.
- A position without its stop loss at Vest, even briefly.
- A login or refresh loop that hammers Vest and gets the account flagged (the Tradovate 2026-09-16 and 2026-09-29
  incidents).
- Secrets in logs, the journal or git.
- **Anything reaching the live server before the owner says so.** In this repo every commit on `main` ships to the
  Chicago VPS by itself (`CLAUDE.md`). This work stays on `feat/vest` until the owner approves the merge.

## Constraints

- The live desk runs on the **Chicago VPS (Linux)**. The session lives there; the owner's signature reaches it through
  the desk page. One new dependency: `cryptography` (P-256 signing), installed on the Mac and the VPS.
- **The owner's wallet is a Coinbase smart wallet (passkey, no recovery phrase).** The signing page connects through
  Coinbase's own wallet library (a keys.coinbase.com pop-up, or a QR for the phone app), which works in any browser,
  Safari included. A browser-extension wallet is offered as a second button. Each wallet step is its own click
  (Safari blocks a second pop-up not started by a click). Vest accepted this wallet's signature (spike, 2026-10-29).
- The 09:10–09:35 ET quiet window and the "flat accounts only" deploy rule apply as they do today.
- Python stack, `httpx` and `websockets` already in `requirements.txt`. Follow the adapter, journal and test patterns
  that `tradovate.py` and `paper.py` use.

## Phase 0: spike (throwaway, on the Mac, demo account)

Before the real build, a throwaway script proves the unknowns. Each answer goes back into this doc:

1. Homebase's own login works: challenge → the owner signs in his wallet → register with Homebase's device key and
   **no Privy token** → the same accounts the site shows (primary, demo, funded).
2. The session survives a day unattended on Homebase's refreshes. Does the refresh move the 30-day end forward?
3. The exact request and response fields of open / close / TP-SL / reads, and the account websocket's messages. Capture
   them while the owner places and cancels one demo order by hand on the site.
4. The funded and demo accounts' loss floors can be read from the API.
5. Vest's API accepts the session from the VPS's IP. Test there last.

If (1) or (5) fails, stop and bring it back to the owner. Those break the chosen route.

**Spike answers (2026-10-29, on the Mac):**

| # | Answer |
|---|---|
| 1 | **Yes.** Register with no Privy token and Homebase's own device key returns 200 with user/access/refresh tokens; `/v3/accounts` works. The wallet login is the owner's existing Vest user (`isNewRegistration: false`). |
| 2 | Refresh with the device signature works (200, new access token ~15 min). **The refresh does NOT move the 30-day end** (`refreshExpiresAtMs` unchanged): the owner re-signs once every 30 days; the desk warns before. |
| 3 | **Open.** The owner has **no Vest Capital account yet** (`/v3/capital/accounts` empty, `isFunded: false`, demo `eligible: false, reason: disabled`); he will buy one. Order/fill fields are captured on the first demo/funded day (plan Task 7), the adapter is built from the site's code and pinned by tests until then. |
| 4 | **Open**, same reason. `capital/limits` only shows counts (`max_eval`, `max_funded`, `max_per_purchase`). `AccountCfg.floors` is the fallback. |
| 5 | Not run (needs the owner's OK; after the purchase). |

Also found:
- **The API symbol is `NDX-USD-PERP`.** `NQ-PERP` is only its `displaySymbol`; `ES-PERP` is `SPX-USD-PERP`.
  `sizeDecimals` 4, `priceDecimals` 2, tick 0.25, taker fee 0.0025 %, maker 0, `capitalTradingStatus` TRADING.
- Price: `GET /v3/ticker/latest?symbols=NDX-USD-PERP` → `tickers[0].markPrice` (also `indexPrice`).
- `/v3/accounts` rows: `account_id`, `account_type`, `amount`, `active`. `account-token` takes `{accountId}`.
- `/v3/executions` and `/v3/trades` return 400 with only `limit`: they need a symbol (or more) — find on demo day.
- Responses also carry an `apiKey` field (a JWT): it is a secret like the tokens and is never logged.

**Where testing happens (assistant's call, the owner did not choose):** everything on the Mac against the Vest Capital
demo account. Step 5 needs one small check script copied to the VPS, **only with the owner's OK** (`CLAUDE.md` forbids
hand-copying otherwise), before any merge to `main`.

**CME price for the held stop entries (assistant's assumption, unconfirmed):** a Tradovate login stays on the desk, so
the existing market-data feed (`data/feed.py`, picked by `desk_app/brokers.md_source`) keeps running. With no Tradovate
login, Vest stop entries cannot fire, and the desk says so instead of trading blind.

## Left to the builder

- The adapter's file split, the account-config fields for a Vest account, and the desk dialog's look (reuse the
  existing **Add account** flow).
- How fills are observed (account websocket vs reads), within the request-rate rules.
- Journal events for the slippage between a held stop entry's level and its Vest fill.

## Calls made by the assistant (the owner can overrule)

- Stop entries are triggered off the **CME** NQ price Homebase already streams, not NQ-PERP's own price.
- The loss-floor guard **refuses new entries** only. It never flattens open positions by itself; their stops at Vest
  do that job.
- NQ-PERP only in the first version.
- **Stop loss and take profit keep the strategy's point distances**, measured from NQ-PERP's own price when the entry
  fires, never the CME prices as they are (NQ-PERP can sit up to ~60 points off CME). If Vest can move a TP/SL in place
  (spike step 3), the adapter re-centres them on the actual fill, as the engine does on Tradovate. If it can't, they
  stay as sent: never delete-then-recreate, which would leave the position unprotected for a moment.
- **When in doubt, skip the trade, never enter late.** A held stop entry fires only while both the CME price feed and
  the Vest session are up. If the level traded while either was down, the entry is skipped and journaled. Held entries
  are saved with the day's state. After a restart they come back only if the price has not yet reached their level.
- **Slippage cap:** a held stop entry is skipped if NQ-PERP is already more than **half the stop distance** past the
  level when it fires. Settable per account. The floor guard checks risk from that price, not the level.
- **Floors not readable from the API:** the account config takes the floors by hand (max drawdown, daily loss limit).
  With neither, the guard **refuses every entry** (it fails closed).
