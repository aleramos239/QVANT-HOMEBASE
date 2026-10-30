"""The Vest option in the Desk's add-account wizard (static files only: no browser, no wallet, no network).
Pins what the wizard must never do with the wallet's signature, and that the vendored Coinbase SDK is one self-contained file."""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "homebase" / "static"
SDK = STATIC / "vendor" / "coinbase-wallet-sdk-4.3.7.js"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
BOOK = (STATIC / "desk" / "book.js").read_text(encoding="utf-8")


def _vest_code() -> str:
    """The wallet half of book.js: from the wallet state to the accounts step."""
    a, b = BOOK.index("const VW = "), BOOK.index("/* The accounts step")
    return BOOK[a:b]


def test_the_vendored_sdk_is_one_file_with_no_remote_imports():
    assert SDK.is_file() and SDK.stat().st_size > 50_000
    src = SDK.read_text(encoding="utf-8")
    assert "createCoinbaseWalletSDK" in src
    assert not re.search(r"""from\s*['"](https?:|/)""", src)                 # export ... from "https://..." / "/v135/..."
    assert not re.search(r"""\bimport\s*['"](https?:|/)""", src)             # bare import "..."
    assert not re.search(r"""\bimport\s*\(\s*['"](https?:|/)""", src)        # dynamic import("...")


def test_step_1_offers_vest_and_the_page_loads_the_sdk_only_when_it_is_chosen():
    assert 'id="optVest"' in INDEX and "wizBroker('vest')" in INDEX and "Your wallet signs in" in INDEX
    assert 'id="envSeg"' in INDEX and 'id="wstep2v"' in INDEX
    assert "Coinbase Wallet" in INDEX and "Browser wallet" in INDEX
    assert "coinbase-wallet-sdk" not in INDEX                                # no <script> for it on any page
    assert 'import("/static/vendor/coinbase-wallet-sdk-4.3.7.js")' in BOOK   # loaded by vestWarm, when Vest is picked
    assert BOOK.count("coinbase-wallet-sdk") == 1
    assert 'WIZ.broker === "vest") vestWarm()' in BOOK


def test_the_demo_live_switch_is_hidden_for_vest_and_comes_back_for_tradovate():
    assert '$("#envSeg").style.display = env === "vest" ? "none" : "";' in BOOK
    assert 'setEnv(WIZ.broker === "vest" ? "vest" : "demo")' in BOOK
    assert 'wizBroker("tv"); wizGoto(1)' in BOOK                              # every opening starts on Tradovate


def test_two_clicks_connect_then_sign():
    code = _vest_code()
    assert code.index('"eth_requestAccounts"') < code.index("/api/vest/challenge") < code.index('"eth_signTypedData_v4"')
    assert code.index('"eth_signTypedData_v4"') < code.index('"/api/connect"')
    assert 'broker: "vest", address: addr, signature: sig' in code
    assert 'appName: "Homebase", appChainIds: [8453], preference: {options: "all"}' in code
    assert "eip6963:announceProvider" in code
    sign = code[code.index("async function vestGo"):code.index("/* a saved Vest login")]
    assert sign.index("eth.request") < sign.index("await post(")               # the pop-up is the first await of the click


def test_the_signature_is_never_kept_or_logged():
    code = _vest_code()
    assert not re.search(r"localStorage|sessionStorage|indexedDB|document\.cookie|console\.|window\.\w+\s*=", code)
    wizard = BOOK[BOOK.index("/* ---- connect wizard"):BOOK.index('$("#connectOverlay").addEventListener')]
    assert not re.search(r"console\.|localStorage|sessionStorage", wizard)
    # `sig` is a local of vestGo, set to null once the POST is back; nothing else mentions a signature but the route's words
    assert re.findall(r"\bsig\b", code) and "VW.sig" not in code and "WIZ.sig" not in BOOK
    assert code.count("let sig = null;") == 1 and "sig = null;\n    if (r.ok)" in code
    for line in code.splitlines():                                            # the word only in comments, the POST body and the route's words
        if "signature" in line:
            assert re.match(r"\s*(/\*|\*|//)", line) or "signature: sig" in line or "new wallet signature" in line \
                or "needs a new signature" in line, line
    # the challenge is good for one try
    assert "VW.typed = null;                      // a challenge is good for one try" in code
    # no key, token or PEM handled in the browser
    assert not re.search(r"apiKey|api_key|PEM|refresh_?token|Authorization", wizard)


def test_step_3_shows_the_kind_and_never_pre_ticks_a_funded_row():
    assert 'Demo' in BOOK and 'funded: "Funded"' in BOOK and 'primary: "Primary"' in BOOK
    acc = BOOK[BOOK.index("function wizAccepted"):BOOK.index("async function doConnect")]
    assert "WIZ.picks = new Set();" in acc                                    # every row starts unticked
    assert "checked" not in acc
    assert 'Add a funded Vest account?' in BOOK                               # and adding one asks first


def test_the_vest_sign_in_says_the_session_lives_on_the_desk_server():
    step = INDEX[INDEX.index('id="wstep2v"'):INDEX.index('id="savedLoginsV"')]
    assert "on the desk server" in step and "this Mac" not in step                 # the desk runs on the VPS (M6)


def test_inside_the_app_the_wallet_buttons_hand_the_sign_in_to_chrome():
    code = _vest_code()
    a = code.index("async function vestConnect(kind)")
    body = code[a:code.index("async function vestGo()")]
    hand = body.index('postMessage({op: "vestSignin"})')
    assert hand < body.index("createCoinbaseWalletSDK") and hand < body.index("vestBrowserProvider()")   # before any wallet
    assert "return;" in body[hand:hand + 250]
    assert "const VAPP = !!(window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.hb);" in BOOK


def test_the_sign_in_window_opens_on_vest_and_closes_itself_only_after_an_add():
    assert 'const VSIGNIN = new URLSearchParams(location.search).get("signin") === "vest";' in BOOK
    assert BOOK.rstrip().endswith('if (VSIGNIN) { openConnect(); wizBroker("vest"); wizGoto(2); }')
    assert 'if (VSIGNIN && r && (r.results || []).some(x => x.status === "added")) setTimeout(() => window.close(), 4000);' in BOOK
    assert BOOK.count("window.close()") == 2                                 # that, and Done / Esc in the sign-in window
