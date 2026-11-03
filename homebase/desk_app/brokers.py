"""The desk's accounts: building adapters, (re)connects through the login budget, failed connects, accounts gone
from their login, removal, the chart service's paper accounts, the reconnect loop and the snapshot refresh.

Moved verbatim from homebase/server.py (module helpers) and homebase.server.create_app (the closures in make())."""
from __future__ import annotations

import asyncio
import contextlib
import weakref
from types import SimpleNamespace

from .. import config as config_mod
from ..broker.alphatrader import ATR_BOOKING_OPEN, TAKEN_LOST, AlphaTraderAdapter
from ..broker.alphatrader_auth import CODE_ASKED, AtrSession
from ..broker.alphatrader_auth import NeedsCode as AtrNeedsCode
from ..broker.base import AccountNotOnLogin, BrokerAdapter
from ..broker.login_budget import LoginDeferred, is_rate_limited
from ..broker.paper import PaperAdapter
from ..broker.topstepx import TSX_BOOKING_OPEN, TopstepXAdapter
from ..broker.topstepx_auth import NeedsCode, TsxSession
from ..broker.tradovate import TradovateAdapter
from ..broker.vest import VestAdapter
from ..broker.vest_auth import NeedsSignature, VestSession
from ..broker.vest_held import _proot
from ..data.feed import MarketFeed

RECONNECT_INTERVAL_S = 5   # cheap now: reconnects reuse the token
GONE_CONFIRM_S = 300       # an account missing from its login is removed only when a 2nd
                           # successful sync at least this much later still misses it
GONE_CHECK_TIMEOUT_S = 30  # a confirming re-sync runs in its own task, at most this long
NOTICES_KEPT = 10
NEEDS_SIGNATURE = "needs a new wallet signature"
NEEDS_CODE = "TopstepX needs a code"
NEEDS_CODE_ATR = CODE_ASKED
_VEST_SESSIONS: dict = {}     # keyring key -> its one VestSession (refresh tokens rotate: one per login)
_TSX_SESSIONS: dict = {}      # keyring key -> its one TsxSession (one token and one socket per login)
_ATR_SESSIONS: dict = {}      # keyring key -> its one AtrSession (one token and one T4 socket per login)
INPLACE_RETRY_S = (10, 60)   # a dropped socket whose token is still valid, while its user's
                             # logins are paused: retry in place 10 s, doubling to 60 s


def is_vest_key(key: str) -> bool:
    """A Vest login: 'vest:<wallet address>'."""
    return key.startswith("vest:")


def is_prop(a) -> bool:
    """A prop-firm eval or funded account (a label only: nothing asks or refuses by it)."""
    n = (a.account_name or "").upper()
    key = a.keyring_key or ""
    return not a.paper and bool(
        a.prop or is_tsx_key(key) or is_atr_key(key) or is_vest_key(key)
        or n.startswith("PA") or any(w in n for w in ("APEX", "LUCID", "TOPSTEP", "FUNDEDNEXT", "ALPHA")))


def vest_session(key: str) -> VestSession:
    """The login's one VestSession, made on first use (R47): build_adapter and the connect routes both take it here."""
    return _VEST_SESSIONS.get(key) or _VEST_SESSIONS.setdefault(key, VestSession(key))


def is_tsx_key(key: str) -> bool:
    """A TopstepX login: 'tsx:<username lowercased>'."""
    return key.startswith("tsx:")


def tsx_session(key: str) -> TsxSession:
    """The login's one TsxSession, made on first use: build_adapter and the connect routes both take it here."""
    return _TSX_SESSIONS.get(key) or _TSX_SESSIONS.setdefault(key, TsxSession(key))


def is_atr_key(key: str) -> bool:
    """An AlphaTrader login: 'atr:<email lowercased>'."""
    return key.startswith("atr:")


def atr_session(key: str) -> AtrSession:
    """The login's one AtrSession, made on first use: build_adapter and the connect routes both take it here."""
    return _ATR_SESSIONS.get(key) or _ATR_SESSIONS.setdefault(key, AtrSession(key))


def _key_env(key: str) -> str:
    """A login key is 'tv:<env>:<user>' — the env it was verified on. The
    user part may itself hold colons (Google-linked logins are
    'Google:1012...'), so split twice at most. A Vest login is 'vest', a TopstepX login 'tsx', an AlphaTrader one 'atr'."""
    if is_vest_key(key):
        return "vest"
    if is_tsx_key(key):
        return "tsx"
    if is_atr_key(key):
        return "atr"
    parts = key.split(":", 2)
    return "live" if len(parts) == 3 and parts[1] == "live" else "demo"


def _md_token_of(ad) -> str:
    tok = getattr(getattr(getattr(ad, "_auth", None), "tokens", None),
                  "md_access_token", "")
    return tok if (tok and ad.connected) else ""


def _md_expiry_of(ad) -> float:
    """Unix expiry of the token the adapter's md token came with; 0 when unknown."""
    try:
        return float(getattr(getattr(getattr(ad, "_auth", None), "tokens", None),
                             "expires_at_unix", 0) or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def md_source(cfg: config_mod.AppCfg, adapters: dict):
    """Market data rides ONE login: its env's md host AND its md token — a
    token only works on its own env's host. Demo first: the proven feed, and
    a live account then needs no md subscription of its own. Within that env,
    the connected login whose token expires LAST (config order on a tie): an
    md socket dies when its token does, so the freshest carries it furthest —
    after the early renewal (09:10-09:19:30 ET) the timer's 09:20 / 09:28:30
    md socket starts on a token that lasts past 10:10. Returns
    (keyring_key, env, token_provider)."""
    ranked = sorted(((aid, a) for aid, a in cfg.accounts.items() if not (is_vest_key(a.keyring_key) or is_tsx_key(a.keyring_key)
                                                                 or is_atr_key(a.keyring_key))),
                    key=lambda kv: kv[1].live)      # a Vest, TopstepX or AlphaTrader login is never a market-data source
    up = [(a, adapters[aid]) for aid, a in ranked
          if a.keyring_key and adapters.get(aid) is not None and _md_token_of(adapters[aid])]
    if up:
        live = up[0][0].live
        a, ad = max((c for c in up if c[0].live == live), key=lambda c: _md_expiry_of(c[1]))
        return (a.keyring_key, "live" if a.live else "demo",
                lambda ad=ad: _md_token_of(ad))
    for aid, a in ranked:            # nothing connected: that login logs in
        if a.keyring_key:
            return a.keyring_key, "live" if a.live else "demo", None
    raise RuntimeError("no accounts configured for market data")


def build_adapter(account_id: str, a: config_mod.AccountCfg) -> BrokerAdapter:
    if a.paper:                      # a chart-service paper account: no login, no broker (broker/paper.py)
        return PaperAdapter(account_id)
    if is_vest_key(a.keyring_key):   # vest_account_id "" = a probe; no floors = every entry refused (fail closed)
        # one session per login, never owned (closed) by an entry: its refresh token rotates (R47)
        return VestAdapter(account_id, keyring_key=a.keyring_key, vest_account_id=a.vest_account_id,
                           session=vest_session(a.keyring_key),
                           floors=dict(a.floors), slip_frac=a.slip_frac)
    if is_tsx_key(a.keyring_key):    # one session (and one socket) per login, shared by every account on it
        return TopstepXAdapter(account_id, keyring_key=a.keyring_key, account_name=a.account_name,
                               session=tsx_session(a.keyring_key), live=a.live)
    if is_atr_key(a.keyring_key):    # one session (and one T4 socket) per login, shared by every account on it
        return AlphaTraderAdapter(account_id, keyring_key=a.keyring_key, account_name=a.account_name,
                                  session=atr_session(a.keyring_key), live=a.live)
    env = "live" if a.live else "demo"
    sel = {"account_name": a.account_name} if a.account_name else None
    # entries on one login share its token: one login / renewal per Tradovate user
    return TradovateAdapter(account_id, env=env, keyring_key=a.keyring_key,
                            account_selector=sel, share_auth=bool(a.keyring_key))


def build_feed(cfg: config_mod.AppCfg, adapters: dict) -> MarketFeed:
    key, env, provider = md_source(cfg, adapters)
    feed = MarketFeed(key, env, token_provider=provider)
    seen = weakref.WeakKeyDictionary()       # Vest adapter -> the socket of its last push
    chosen: dict[str, tuple] = {}            # price root -> the (minutes, root) stream passed on (R44)

    def to_vest(root: str, bar) -> None:
        """The CME price for the Vest held entries. It reaches whatever adapter the desk holds for each account NOW
        (a rebuilt one replaces the old: one book per account, never two), on this socket's loop -- the desk's loop,
        where the adapters live. ONE stream per price root (NQ and MNQ are one price): HeldBook keeps one last push per
        price root, two streams interleaved would each look like a new bar (R44)."""
        pr = _proot(root)
        pick = min(((m, r) for r, m in feed.watching() if _proot(r) == pr), default=(bar.minutes, root))
        if (bar.minutes, root) != pick:
            return
        if chosen.setdefault(pr, pick) != pick:  # the stream changed (a smaller one was enabled): a first push for all
            chosen[pr] = pick
            seen.clear()
        for ad in list(adapters.values()):
            if not isinstance(ad, VestAdapter):
                continue
            if seen.get(ad) is not feed._ws:     # its first push on this socket: a (re)connect is a gap (R1)
                seen[ad] = feed._ws
                ad.feed_ok = lambda: feed.connected
                ad.feed_bars = feed.bars         # the restore reads the bars since the book's save (R62)
                ad.feed_reset()
            ad.on_bar(root, bar)

    feed.bar_listeners.append(to_vest)
    return feed

def make(*, cfg, engine, adapters, acct_status, budget, desk, paper_http, paper_client, background,
         adapter_factory, _kill_lock) -> SimpleNamespace:
    _logged_in_once: set[str] = set()        # entries that logged in / rode the shared token
    _login_first_spent: set[tuple] = set()   # (login key, live): its one exempt first login
    _went_private: set[str] = set()          # entries refused on the shared token
    _parked: dict[str, str] = {}             # entry -> why (its account is not on its login)
    # entry -> its account-gone state: first/next_check (unix), unbooked, confirmed
    _gone: dict[str, dict] = {}
    _no_accounts_warned: set[str] = set()
    notices: list[dict] = []                 # one-liners for the desk page (status payload)

    def _notice(text: str, **kw) -> None:
        notices.append({"et": engine.now_et().isoformat(timespec="seconds"),
                        "text": text, **kw})
        del notices[:-NOTICES_KEPT]

    def _short(aid: str) -> str:
        a = cfg.accounts.get(aid)
        name = (a.account_name if a is not None else "") or aid
        return "…" + name[-3:] if len(name) > 6 else name

    def _login_label(aid: str) -> str:
        if is_tsx_key(_login_key(aid)):
            return "TopstepX"
        if is_atr_key(_login_key(aid)):
            return "AlphaTrader"
        tail = _login_key(aid).rsplit(":", 1)[-1].split("_", 1)[0]
        return tail.capitalize() if tail else "Tradovate"

    def _check_at(aid: str) -> str:
        return "AlphaTrader" if is_atr_key(_login_key(aid)) else "Tradovate"     # TopstepX's words stay as they were

    _listed: dict[str, set[str]] = {}        # login key -> account names its last probe listed
    _add_lock = asyncio.Lock()               # one "add accounts" at a time

    def _on_desk(key: str, name: str) -> str | None:
        """The desk entry that already carries this broker account of this login: pinned
        to it, or -- unpinned -- riding it (the connected adapter says which)."""
        low = name.lower()
        for aid, a in cfg.accounts.items():
            if a.keyring_key != key:
                continue
            pinned = a.account_name or getattr(adapters.get(aid), "_acct_name", "") or ""
            if pinned.lower() == low or aid == low:
                return aid
        return None

    _login_uid: dict[str, object] = {}       # login key -> the Tradovate user id first seen
    _login_suspect: set[str] = set()         # login keys already warned "may have changed"
    _gone_tasks: dict[str, asyncio.Task] = {}

    def _login_key(aid: str) -> str:
        a = cfg.accounts.get(aid)
        return (a.keyring_key if a is not None else "") or aid

    _connect_locks: dict[str, asyncio.Lock] = {}

    async def _connect_account(aid: str, force_login: bool = False,
                               manual: bool = False) -> str:
        """One (re)connect per account at a time (the supervisor, a manual Reconnect and
        a gone re-check can race), and never for an account no longer on the desk."""
        async with _connect_locks.setdefault(aid, asyncio.Lock()):
            if aid not in cfg.accounts:
                raise RuntimeError(f"{aid} is no longer on the desk")
            return await _connect_account_locked(aid, force_login, manual)

    async def _connect_account_locked(aid: str, force_login: bool = False,
                                      manual: bool = False) -> str:
        """(Re)connect one account. Prefers an in-place reconnect on the token
        it already holds — no login spent — and only falls back to a full
        login. A drop used to cost a full login every time: ~20/hour on a
        sleeping laptop against Tradovate's ~5/hour limit. Every login goes
        through the user's LoginBudget (429 cool-down, hourly cap, backoff;
        `manual` skips only the backoff); refused, it raises LoginDeferred."""
        a = cfg.accounts[aid]
        key = _login_key(aid)
        ad = adapters.get(aid)
        if ad is None:
            ad = adapters[aid] = adapter_factory(aid, a)
        if hasattr(ad, "login_budget") and ad.login_budget is not budget:
            ad.login_budget = budget        # the token refresh's login fallback asks it too
        if isinstance(ad, VestAdapter):
            ad.journal = engine.journal     # its held-entry fires and skips go on the desk's journal
            ad.session.budget = budget      # the login's one session books on the desk's budget (R48)
        elif isinstance(ad, (TopstepXAdapter, AlphaTraderAdapter)):
            ad.journal = engine.journal     # tsx_violation / atr_*
            ad.session.budget = budget      # every TopstepX login (first, renewal, after a 401 or a kick) is booked on it
            ad.session.journal = engine.journal     # tsx_session_taken

        login_id = (key, a.live)

        async def _login(fell_back_from=None) -> None:
            if a.paper:              # nothing to log in to: the chart service's book, no budget spent
                await ad.connect()
                return
            # the cap/backoff exemption is ONE first login per Tradovate login per process
            # (its entries share the token), never for an entry that went private
            first = (aid not in _logged_in_once and login_id not in _login_first_spent
                     and aid not in _went_private)
            # a TopstepX session that holds a token sends no /Login on connect: nothing to refuse (a renewal or a
            # re-login still asks the budget, in the session). An AlphaTrader adapter joining its login's T4 socket while it
            # is up sends no login either; a socket that must log in books it itself (session and socket ask the budget)
            holds = ((isinstance(ad, TopstepXAdapter) and ad.session._token is not None)
                     or (isinstance(ad, AlphaTraderAdapter) and ad.session.socket is not None and ad.session.socket.up))
            why = None if holds else budget.blocked(key, first=first, manual=manual)
            if why:
                raise LoginDeferred(why if fell_back_from is None else
                                    f"{str(fell_back_from)[:120]} — no login fallback: {why}")
            if fell_back_from is not None:
                engine.journal("reconnect_fell_back_to_login", account=aid,
                               error=str(fell_back_from)[:200])
            _logged_in_once.add(aid)
            _login_first_spent.add(login_id)
            # A Vest connect mints a token on the signed session: no login (R6). A TopstepX connect sends /Login only
            # when its session holds no token, and that session books it (session.budget) -- booked here too it counts twice.
            if not isinstance(ad, (VestAdapter, TopstepXAdapter, AlphaTraderAdapter)):
                budget.record_login(key)
            try:
                await (ad.connect(manual=manual) if isinstance(ad, AlphaTraderAdapter) else ad.connect())
            except (AccountNotOnLogin, NeedsSignature):
                budget.login_result(key)    # the login itself worked / none was tried (the wallet must sign): no backoff
                raise
            except Exception as e:  # noqa: BLE001
                if not isinstance(ad, (TopstepXAdapter, AlphaTraderAdapter)):   # its session already booked a failed login
                    budget.login_result(key, e)
                raise
            budget.login_result(key)

        mode = "login"
        has_token = bool(getattr(getattr(ad, "_auth", None), "tokens", None))
        if has_token and not force_login and hasattr(ad, "reconnect"):
            try:
                await ad.reconnect()
                mode = "reconnect"
                _logged_in_once.add(aid)           # on the shared token: the login's
                _login_first_spent.add(login_id)   # first login is spent already
            except AccountNotOnLogin:
                # Permanent: the pin is wrong for THIS login, not a dropped
                # socket. A full login would just burn the shared keyring
                # login (other pins on it need it) chasing a pin that will
                # never be there — never retry it as a transient drop.
                raise
            except Exception as e:  # noqa: BLE001 — fall back to a real login
                budget.note_error(key, e)          # a 429 cools the whole user down
                if (getattr(ad, "auth_shared", False) and "authorize failed" in str(e)
                        and not is_rate_limited(e)):
                    # the shared token was refused on THIS socket: its login must never
                    # re-roll the token every sibling rides -- a private one, budgeted
                    ad.go_private()
                    _went_private.add(aid)
                    engine.journal("shared_token_refused", account=aid, error=str(e)[:200])
                await _login(fell_back_from=e)
        else:
            await _login()
        await ad.observe_fills(engine.on_fill)
        if not a.paper:              # the chart page trades a paper account through its own book, never the desk
            desk.attach(aid, ad)
        _parked.pop(aid, None)
        _inplace_streak.pop(aid, None)
        _no_accounts_warned.discard(aid)
        uid = getattr(getattr(getattr(ad, "_auth", None), "tokens", None), "user_id", None)
        if uid:
            _login_uid.setdefault(key, uid)
        g = _gone.pop(aid, None)
        if g is not None:
            restored = []
            # a TopstepX or AlphaTrader account is never booked yet
            rebook = (TSX_BOOKING_OPEN or not is_tsx_key(key)) and (ATR_BOOKING_OPEN or not is_atr_key(key))
            for name, rows in (g.get("booked") or {}).items() if rebook else ():
                have = cfg.book.setdefault(name, [])
                for r in rows:
                    if not any(x.get("account") == aid for x in have):
                        have.append(dict(r))
                        restored.append(name)
            if restored:
                config_mod.save(cfg)
            engine.journal("account_back", account=aid, rebooked=restored)
            _notice(f"{_short(aid)} is back on your {_login_label(aid)} login", account=aid)
        acct_status[aid] = {"connected": True, "error": None}
        engine.journal("broker_connected", account=aid,
                       broker_account=a.account_name, mode="paper" if a.paper else mode)
        try:
            await engine.reconcile_account(aid)
        except Exception as e:  # noqa: BLE001 — never block the connect on it
            engine.journal("reconcile_error", account=aid, error=str(e)[:200])
        return mode

    _login_cooldown: dict[str, float] = {}   # account id -> unix ts of next try
    _inplace_streak: dict[str, int] = {}     # failed in-place-only retries in a row

    def _token_left(aid: str) -> float:
        import time as _t
        tokens = getattr(getattr(adapters.get(aid), "_auth", None), "tokens", None)
        exp = getattr(tokens, "expires_at_unix", 0) or 0
        return exp - _t.time() if exp else 0.0

    def _connect_failed(aid: str, e: Exception) -> None:
        """Record a failed (re)connect. An account missing from its login is PARKED:
        never retried automatically (the loop would log in on the shared user every
        few minutes forever -- apex...049, closed at Apex, 2026-09-29), only by a
        manual Reconnect, once per click."""
        import time as _t
        if aid not in cfg.accounts:
            return                           # removed meanwhile: nothing to record
        msg = str(e)
        if isinstance(e, NeedsSignature):
            # retried by the loop as soon as the login is signed again, never before (no cooldown to wait out)
            if (acct_status.get(aid) or {}).get("error") != NEEDS_SIGNATURE:
                engine.journal("vest_needs_signature", account=aid)
            acct_status[aid] = {"connected": False, "error": NEEDS_SIGNATURE}
            _login_cooldown.pop(aid, None)
            return
        if isinstance(e, NeedsCode):
            # the login stays asked for a code until the owner answers it in the wizard: never retried soon
            if (acct_status.get(aid) or {}).get("error") != NEEDS_CODE:
                engine.journal("tsx_needs_code", account=aid)
            acct_status[aid] = {"connected": False, "error": NEEDS_CODE}
            _login_cooldown[aid] = _t.time() + 1800
            return
        if isinstance(e, AtrNeedsCode):
            if (acct_status.get(aid) or {}).get("error") != NEEDS_CODE_ATR:
                engine.journal("atr_needs_code", account=aid)
            acct_status[aid] = {"connected": False, "error": NEEDS_CODE_ATR}
            _login_cooldown[aid] = _t.time() + 1800
            return
        if isinstance(e, AccountNotOnLogin):
            a = cfg.accounts.get(aid)
            name = (a.account_name if a is not None else "") or aid
            if aid not in _parked:
                engine.journal("account_parked", account=aid, error=msg[:200])
            _parked[aid] = msg
            _login_cooldown.pop(aid, None)
            acct_status[aid] = {"connected": False, "parked": True,
                                "error": f"account {name} is not on this login — "
                                         f"remove it from the desk ({msg[:160]})"}
            _note_gone(aid, e)
            return
        if "login exposes no accounts" in msg:
            # never evidence that an account is gone: warn, act on nothing
            if aid not in _no_accounts_warned:
                _no_accounts_warned.add(aid)
                engine.journal("login_lists_no_accounts", account=aid, login=_login_key(aid))
                _notice(f"your {_login_label(aid)} login listed no accounts — nothing was "
                        f"removed; check the login at {_check_at(aid)}", account=aid, level="warn")
        acct_status[aid] = {"connected": False, "error": msg}
        if isinstance(e, LoginDeferred) and _token_left(aid) > 120:
            # the socket dropped, its token is still good, only the login fallback was
            # refused (a 429 cool-down, the cap): no login is spent retrying in place,
            # so do it soon -- a healthy entry must not sit out 5 minutes before the fire
            n = _inplace_streak[aid] = _inplace_streak.get(aid, 0) + 1
            lo, hi = INPLACE_RETRY_S
            _login_cooldown[aid] = _t.time() + min(lo * 2 ** (n - 1), hi)
            return
        # NEVER hammer the login endpoint: auth rejections and rate-limit
        # tickets wait 30 min; anything else 5 min (the user's LoginBudget
        # gates the login itself on top of this)
        slow = ("Login failed" in msg or "p-ticket" in msg or "p-captcha" in msg)
        _login_cooldown[aid] = _t.time() + (1800 if slow else 300)

    def _note_gone(aid: str, e: AccountNotOnLogin) -> None:
        """A successful sync listed the login's accounts and this entry's is not among
        them. The first sighting parks it and journals account_gone; one at least
        GONE_CONFIRM_S later confirms: _gone_step then unbooks and removes it. Never evidence: a failed, 429'd or empty sync (no listing), a login
        whose Tradovate user changed, or one where not only a MINORITY of the login's
        pinned entries is missing -- that is a changed login, not a closed account: park,
        warn, touch nothing."""
        import time as _t
        listed = getattr(e, "listed", None)
        if not listed or aid not in cfg.accounts:
            return
        key, live = _login_key(aid), cfg.accounts[aid].live
        pins = {x: (a.account_name or "").lower() for x, a in cfg.accounts.items()
                if _login_key(x) == key and a.live == live and a.account_name}
        have = {str(n).lower() for n in listed}
        missing = [x for x, pin in pins.items() if pin not in have]
        uid, was = getattr(e, "user_id", None), _login_uid.get(key)
        if (uid and was and uid != was) or 2 * len(missing) >= len(pins):
            _gone.pop(aid, None)
            if key not in _login_suspect:
                _login_suspect.add(key)
                engine.journal("login_changed_suspect", login=key, missing=missing,
                               user_changed=bool(uid and was and uid != was),
                               login_lists=list(listed))
                _notice(f"your {_login_label(aid)} login no longer lists "
                        f"{', '.join(_short(x) for x in missing) or _short(aid)} — the login may "
                        f"have changed; nothing was unbooked or removed. Check it at {_check_at(aid)}",
                        account=aid, level="warn")
            return
        now = _t.time()
        g = _gone.get(aid)
        if g is None:
            _gone[aid] = {"first": now, "next_check": now + GONE_CONFIRM_S,
                          "confirmed": False, "listed": list(listed)}
            engine.journal("account_gone", account=aid, login_lists=list(listed))
            _notice(f"{_short(aid)} is no longer on your {_login_label(aid)} login — parked; "
                    "removed from the desk if a second check agrees", account=aid)
        elif now - g["first"] >= GONE_CONFIRM_S:
            g["confirmed"] = True

    async def _drop_account(aid: str, **journal_extra) -> None:
        """Unassign an entry from every strategy, drop it from the pool, close it. An
        in-flight gone re-check is cancelled first, and the account's connect lock is
        held, so a removed adapter is never reconnected behind the removal. Also waits
        for the Kill lock (2026-09-29 review): the Kill sweep reads `adapters` and calls
        each one's cancel_all/flatten_all in turn, so a removal mid-sweep must wait its
        turn rather than pop an entry out from under it (this covers every removal path,
        the manual endpoint AND the gone-account auto-removal below, alike)."""
        t = _gone_tasks.pop(aid, None)
        if t is not None and not t.done():
            t.cancel()
            with contextlib.suppress(BaseException):
                await t
        async with _kill_lock(), _connect_locks.setdefault(aid, asyncio.Lock()):
            await _drop_account_locked(aid, **journal_extra)
        _connect_locks.pop(aid, None)

    async def _drop_account_locked(aid: str, **journal_extra) -> None:
        for name in list(cfg.book):
            cfg.book[name] = [a for a in cfg.book[name]
                              if a.get("account") != aid]
        cfg.accounts.pop(aid, None)
        config_mod.save(cfg)
        acct_status.pop(aid, None)
        _parked.pop(aid, None)
        _gone.pop(aid, None)
        _login_cooldown.pop(aid, None)
        old = adapters.pop(aid, None)
        if old is not None:
            with contextlib.suppress(Exception):
                await old.close()
        engine.journal("account_removed", account=aid, **journal_extra)

    async def _gone_check(aid: str) -> None:
        """One confirming re-sync, in its own task: it never holds the supervisor."""
        try:
            await asyncio.wait_for(_connect_account(aid), GONE_CHECK_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001 — _note_gone judges it
            _connect_failed(aid, e)

    async def _gone_step() -> None:
        """Accounts that left their login: one confirming re-sync GONE_CONFIRM_S after the
        first sighting, then -- confirmed -- unbook and remove. The bookings are kept in case it
        comes back."""
        import time as _t
        if not _gone:
            return
        now_et = engine.now_et()
        for aid, g in list(_gone.items()):
            if aid not in cfg.accounts:
                _gone.pop(aid, None)
                continue
            if g["confirmed"]:
                g["booked"] = {n: [dict(r) for r in rows if r.get("account") == aid]
                               for n, rows in cfg.book.items()
                               if any(r.get("account") == aid for r in rows)}
                line = (f"{_short(aid)} is no longer on your {_login_label(aid)} login — "
                        "removed from the desk")           # worded before the entry goes
                await _drop_account(aid, reason="not on the login any more",
                                    unbooked=sorted(g["booked"]))
                _notice(line, account=aid)
                continue
            t = _gone_tasks.get(aid)
            if (t is None or t.done()) and _t.time() >= g["next_check"]:
                g["next_check"] = _t.time() + GONE_CONFIRM_S
                _gone_tasks[aid] = asyncio.create_task(_gone_check(aid))

    async def _sync_paper() -> None:
        """Every chart-service paper account is an account of the desk's pool (assignable to an algo in
        + Assign) -- one per paper id, labelled "<name> (paper)". Added here, never by hand; removed only
        with the account on the Charts page (its adapter then fails to read the book and drops out of
        the readiness checks). A service that is down adds nothing."""
        if not (background or paper_client is not None):
            return                   # a test app reaches no service it was not handed
        try:
            r = await paper_http.get("/api/paper/accounts")
            r.raise_for_status()
            rows = r.json()["accounts"]
        except Exception:  # noqa: BLE001 — the chart service is down: the adapters say so themselves
            return
        for row in rows:
            aid = str(row["id"])
            if aid in cfg.accounts or aid == "paper":   # the built-in PAPER is chart trading's own (owner, 2026-10-20)
                continue
            label = str(row.get("label") or aid)
            cfg.accounts[aid] = config_mod.AccountCfg(paper=True, label=f"{label} (paper)", account_name=label)
            config_mod.save(cfg)
            engine.journal("account_added", account=aid, live=False, paper=True)
        gone = {aid for aid, a in cfg.accounts.items() if a.paper} - {str(r["id"]) for r in rows}
        for aid in gone:
            acct_status[aid] = {"connected": False, "error": "this paper account no longer exists on the Charts page"}

    async def _broker_loop():
        import time as _t
        while True:
            budget.tick()                    # a cool-down's one "ended" line
            with contextlib.suppress(Exception):
                await _sync_paper()
            try:
                await _gone_step()
            except Exception as e:  # noqa: BLE001 — never kill the supervisor
                engine.journal("account_gone_error", error=str(e)[:200])
            for aid in list(cfg.accounts):
                if aid in _parked:
                    continue                 # only a manual Reconnect retries it
                ad = adapters.get(aid)
                if isinstance(ad, VestAdapter) and ad.session.needs_signature:
                    if ad.connected:         # the login ran out while connected: the card must say so (R46)
                        with contextlib.suppress(Exception):
                            await ad.close()
                        _connect_failed(aid, NeedsSignature("sign with the wallet again"))
                    continue                 # waits for the owner's wallet signature
                if isinstance(ad, TopstepXAdapter) and ad.session.lost is not None and ad.connected:
                    # a kick whose re-login was deferred or asked for a code: the card shows the account disconnected,
                    # with the reason; the reconnect logs in again first (through the budget)
                    with contextlib.suppress(Exception):
                        await ad.close()
                    _connect_failed(aid, ad.session.lost)
                    continue
                lost = ad.session.lost if isinstance(ad, AlphaTraderAdapter) else None
                # the same for AlphaTrader: its T4 socket down with a reason (a deferred login, a code, a refusal); a kicked
                # session logging in again by itself is not lost
                if lost and ad.connected and not ad._up() and not lost.startswith(TAKEN_LOST):
                    with contextlib.suppress(Exception):
                        await ad.close()
                    _connect_failed(aid, AtrNeedsCode(lost) if lost == NEEDS_CODE_ATR else RuntimeError(lost))
                    continue
                if ad is not None and ad.connected:
                    continue
                if _t.time() < _login_cooldown.get(aid, 0):
                    continue
                try:
                    await _connect_account(aid)
                    _login_cooldown.pop(aid, None)
                except Exception as e:  # noqa: BLE001 — report, back off
                    _connect_failed(aid, e)
            await asyncio.sleep(RECONNECT_INTERVAL_S)

    async def _refresh_snapshots() -> None:
        """The caches' slow refresh: ONE position/list + cashBalance/list per
        Tradovate user (its lists cover every account under the login), on the first
        connected entry that can do it. Skipped for a user in a 429 cool-down."""
        by_user: dict[tuple, list] = {}
        for aid, ad in list(adapters.items()):
            if aid in cfg.accounts and ad.connected and hasattr(ad, "refresh_snapshot"):
                by_user.setdefault((_login_key(aid), cfg.accounts[aid].live), []).append(ad)
        for (key, _live), ads in by_user.items():
            if budget.cooling(key):
                continue
            try:
                await ads[0].refresh_snapshot(ads[1:])
            except Exception as e:  # noqa: BLE001 — the pushes still carry the caches
                budget.note_error(key, e)

    return SimpleNamespace(notices=notices, listed=_listed, add_lock=_add_lock, on_desk=_on_desk,
                           login_first_spent=_login_first_spent, login_cooldown=_login_cooldown, parked=_parked,
                           gone=_gone, login_uid=_login_uid, connect_account=_connect_account,
                           connect_failed=_connect_failed, drop_account=_drop_account, gone_step=_gone_step,
                           sync_paper=_sync_paper, broker_loop=_broker_loop, refresh_snapshots=_refresh_snapshots)
