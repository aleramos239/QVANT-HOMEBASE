# TopstepX (Topstep) connection — design

Date: 2026-10-30. Branch: `feat/topstepx` (worktree `.worktrees/topstepx`). Status: draft with the owner's answers, waiting for his approval.

## Intent

The owner wants to connect his **Topstep** accounts to Homebase, "just like how we just added the tradovate login and vest
market log in" (owner, 2026-10-30). Topstep accounts trade on **TopstepX** (Topstep's own platform, built by ProjectX).
This project builds the **connection** only: a TopstepX account that sits on the desk like a Tradovate or Vest account, and
that any strategy can later be booked on.

Like Tradovate and Vest it works **without the paid API key** (the owner has none: "i have no api key, build it like how you
built the tradovate or vest markets connection", 2026-10-30). Homebase logs in the way the TopstepX website does, with the
owner's TopstepX username and password. The owner accepts that Topstep may treat this as unofficial access (account flagged,
closed or payouts lost), the same risk he accepted for Tradovate and Vest.

**Alpha Futures is out** (owner, 2026-10-30, "Topstep only for now"): no API since ProjectX left them on 2026-02-28, and
Alpha's rules ban automated trading. It comes back only if Alpha says in writing that automation is allowed.

## What we know about TopstepX (read from the live site's code, 2026-10-30)

From `https://topstepx.com/static/main-*.js` and `https://topstepx.com/config.json`:

- **Servers:** `userApi` = `https://userapi.topstepx.com` (accounts, orders, positions, trades, login);
  `chartApi` = `https://chartapi.topstepx.com` (charts, market data; Homebase does not need it).
- **Login:** `POST /Login` with JSON `{userName, password}`; the answer carries `userId`, a token, `result` and
  `errorMessage`. Other calls send `Authorization: Bearer <token>`. `GET /Session/validate` checks a session. **No captcha
  and no FingerprintJS on the login.** (`/Login/key` is the paid-API login; not used.) Some login models carry a `code`
  field, so a one-time code (email / 2FA) step may exist: the spike checks.
- **Accounts:** `GET /TradingAccount` lists the user's accounts; `/TradingAccount/buyingPower/{id}`,
  `/TradingAccount/personalLimits`, `/RiskSettingsLockout/active/{id}`.
- **Orders:** `POST /Order` with `{accountId, symbolId, contractId, type, positionSize, limitPrice, stopPrice,
  trailDistance, customTag, linkedOrderId, timeType, stopLoss, takeProfit, positionBracket}`. **The stop loss and take
  profit ride on the entry order itself**, so a position is protected the moment it fills. Stop entries exist natively
  (unlike Vest). Cancel: `/Order/cancel/{accountId}/id/{orderId}`, `/all`, `/contract/{contractId}`; move a stop:
  `/Order/editStopLoss`.
- **Positions and trades:** `/Position/all/account/{accountId}`, `/Position/close/{accountId}` (flatten),
  `/Position/close/{accountId}/contract/{contractId}`; `/Trade/id/{accountId}`, `/Trade/range`.
- **Live updates:** a SignalR websocket (`/hubs/account`, `skipNegotiation`, token in `accessTokenFactory`) pushing
  `RealTimeOrder`, `RealTimePosition`, `RealTimeTrade`, `RealTimeAccount`, `RealTimeTradingAccountViolation`,
  `RealTimeSession` and more, after `SubscribeAccounts`.
- **One device session at a time:** the site tells a user "Exchange regulations permit only one active device session at a
  time. You have been disconnected". So Homebase being logged in may kick the owner's own TopstepX browser or phone out,
  or the reverse. **The owner accepted this (2026-10-30: "Yes, that's fine").**
- The owner signs in to TopstepX with a **username + password on topstepx.com** (owner, 2026-10-30), not through topstep.com
  single sign-on, so `POST /Login` is his route.

Not known yet (the first build step is a spike against the owner's real login, read-only): the token's lifetime and how the
site renews it, whether a one-time code is asked, the numbers for `type` / side / `timeType`, the exact hub host and frame
format, and what a contract id looks like for NQ / MNQ / ES / MES / GC / MGC.

## Goals

1. A TopstepX adapter (`homebase/broker/topstepx*.py`) implementing `BrokerAdapter` (`homebase/broker/base.py`), built by
   `build_adapter` in `homebase/desk_app/brokers.py` for an account whose login key starts `tsx:`.
2. **Login exactly like Tradovate:** username + password, checked by a real login, stored in `secrets_store` under
   `tsx:<username>` (never in git, logs or the journal). Homebase renews the token by itself; when it cannot, it logs in
   again with the saved password, through the login budget.
3. **The same desk wizard and routes** (`homebase/routes/accounts.py`, the `wstep*` steps in `homebase/static/index.html`):

   | Step | Tradovate today | TopstepX |
   |---|---|---|
   | 1. Pick the broker | Tradovate / Paper / Vest | adds **TopstepX** |
   | 2. Log in | username + password (`/api/connect`) | username + password (`/api/connect`), plus a code box only if TopstepX asks for one |
   | Saved login | `tv:<env>:<user>`, listed, reusable, deletable | `tsx:<user>`, the same |
   | 3. Tick accounts | every account under the login | every TopstepX account under the login (combines, Express Funded, Live Funded) |
   | Added accounts | `AccountCfg` entries, never booked | the same |
   | Reconnect / Remove | through the login budget | the same paths and the same budget |

4. **Orders:** market, limit, stop and stop-limit entries go to TopstepX as they are, with the strategy's stop loss and take
   profit attached to the entry order. Flatten, cancel-all, cancel by id, move stop, net position and balance as the desk
   needs them today.
5. **Every position has its stop loss at TopstepX from the moment it opens.** Never an unprotected position.
6. **Fills** come from the account socket (`RealTimeTrade` / `RealTimeOrder` / `RealTimePosition`) into `observe_fills`,
   the same `FillEvent` shape Tradovate gives.
7. **Low request rate from day one**, the Tradovate lessons (`docs/superpowers/GOTCHAS.md`; findings 2026-09-16 and
   2026-09-29): one login and one socket per TopstepX login shared by all its accounts; a login budget with backoff after
   failures and 429s; status reads from caches, never broker calls on page refresh.
8. **Kicked out: always take it back** (owner, 2026-10-30, "Always take it back"). When TopstepX ends Homebase's session
   because the owner opened the site or app elsewhere (`RealTimeSession` / a 401 on the socket or a call), Homebase logs back
   in right away with the saved password. The login budget still caps it (backoff after failures and 429s, the hourly cap), so
   a ping-pong with the owner's browser is accepted but can never become a login flood. Each kick is journaled
   (`tsx_session_taken`) and counted on the account card.
9. **Topstep's 15:10 CT (16:10 ET) forced close: Topstep does it** (owner, 2026-10-30, "Let Topstep close them"). The desk
   adds no cutoff of its own for TopstepX accounts; Topstep's close reaches Homebase as an outside fill and is handled the way
   the desk handles any outside fill today.
10. **Testing order:** a Topstep combine (practice/eval) account first. A funded account is booked only when the owner says so.

### Calls made by the designer (the owner may overrule)

- **One-time code:** if TopstepX asks for a code at login, the wizard shows a code box. If a re-login needs one, that login's
  accounts stop and the card says "TopstepX needs a code" (like Vest's "needs a new signature") until the owner enters it.
- **The spike:** the owner types his own password into the wizard (Homebase never asks for it in chat). The spike only reads
  (accounts, positions, the socket). The first real order on a combine goes only on the owner's word, with him watching.
- **Prop rules:** no Topstep rule set for the prop sim in this project; the account gets the desk's existing defaults. Adding
  Topstep's rules is a separate job.

## Non-goals

- TopstepX market data or charts. Charts and signals keep using Homebase's own CME data; a TopstepX login is never a
  market-data source (`md_source` skips it, as it skips Vest).
- The paid ProjectX API (`/Login/key`, `api.topstepx.com`).
- Alpha Futures, or any other ProjectX firm.
- Chart trading on TopstepX (the adapter may leave those methods at their "not supported" defaults), unless it falls out
  for free.
- Choosing or testing strategies (blueprint work, separate).
- A new loss-floor guard. TopstepX accounts get the desk's existing per-account rules, like Tradovate prop accounts.

## Anti-goals: failure even if it "works"

- A Homebase bug, a missed fill or a doubled order breaks Topstep's loss limit and closes the account.
- A position without its stop loss at TopstepX, even briefly.
- A login loop that hammers TopstepX and gets the account flagged (taking the session back always goes through the budget).
- The password or token in logs, the journal or git.
- **Anything reaching the live server before the owner says so.** Every commit on `main` ships to the Chicago VPS by itself
  (`CLAUDE.md`). This work stays on `feat/topstepx` until the owner approves the merge.

## Constraints

- The live desk runs on the Chicago VPS (Linux); the login and socket live there. Python, `httpx` and `websockets` are
  already in `requirements.txt`; SignalR's JSON protocol is small enough to speak over `websockets` (no new dependency).
- The 09:10–09:35 ET quiet window and the "flat accounts only" deploy rule apply as today.
- Follow the adapter, journal and test patterns of `tradovate*.py` and `vest*.py`; tests never reach TopstepX (an autouse
  guard like `tests/test_vest*`).

## Left to the builder

- File split (`topstepx.py` adapter, `topstepx_auth.py` login/renewal, `topstepx_ws.py` socket), the SignalR client, symbol
  to contract-id mapping, and how the code step (if any) fits the wizard.
- What the desk shows for TopstepX's own rule breaches (`RealTimeTradingAccountViolation`, lockouts): at least a journal line
  and the account card's status.
