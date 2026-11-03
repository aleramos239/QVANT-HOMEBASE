"""The TopstepX option in the Desk's add-account wizard (static files only: no browser, no network)."""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "homebase" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
BOOK = (STATIC / "desk" / "book.js").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    a = BOOK.index(name)
    return BOOK[a:BOOK.index("\n}\n", a)]


def test_step_1_offers_topstepx():
    assert '<div class="opt" id="optTsx" onclick="wizBroker(\'tsx\')">' in INDEX
    opt = INDEX[INDEX.index('id="optTsx"'):INDEX.index('id="optPaper"')]
    assert '<span class="glyph">Tx</span>' in opt and "TopstepX" in opt and "Username &amp; password" in opt
    # step 2: a hidden one-time-code row, outside the new-login fields so a saved login can answer it too
    row = INDEX[INDEX.index('id="cCodeRow"'):INDEX.index('<div class="row-btns">', INDEX.index('id="cCodeRow"'))]
    assert 'style="display:none"' in INDEX[INDEX.index('id="cCodeRow"') - 20:INDEX.index('id="cCodeRow"') + 60]
    assert "Code from TopstepX" in row and 'id="cCode"' in row and 'autocomplete="off"' in row
    assert INDEX.index('id="newLoginFields"') < INDEX.index('id="cCodeRow"') < INDEX.index('id="cGo"')
    assert 'id="wstep2"' in INDEX and 'id="wBroker2"' in INDEX
    assert 'book.js?v=14' in INDEX


def test_the_env_switch_is_hidden_for_tsx():
    assert 'WIZ.broker = b === "vest" ? "vest" : b === "tsx" ? "tsx" : b === "atr" ? "atr" : "tv";' in BOOK
    assert '$("#optTsx").classList.toggle("sel", WIZ.broker === "tsx");' in BOOK
    assert 'setEnv(WIZ.broker === "tv" ? "demo" : WIZ.broker);' in BOOK
    assert '$("#envSeg").style.display = env === "vest" || env === "tsx" || env === "atr" ? "none" : "";' in BOOK
    assert "A TopstepX login lists every account under it. Nothing trades until you assign it to a strategy." in BOOK
    assert "Log in to TopstepX" in BOOK
    assert 'wizBroker("tv"); wizGoto(1)' in BOOK                              # every opening starts on Tradovate
    assert 'l.env === "tsx" ? "TopstepX"' in BOOK                              # a saved tsx: login is labelled in words


def test_doConnect_sends_broker_tsx_and_the_code():
    body = _fn("async function doConnect")
    assert 'broker: "tsx"' in body and "code" in body
    assert 'WIZ.broker === "tsx"' in body
    # the code row shows only after a needs_code answer, takes focus, and the next Connect sends the code
    assert "r.needs_code" in body and "TopstepX sent you a code — type it in" in body
    assert 'codeRow.style.display = ""' in body and "$(\"#cCode\").focus()" in body
    # a saved login answers the code through its saved key; a new one with the same username and password
    assert "{saved_key: WIZ.saved, ...withCode}" in body
    assert not re.search(r"console\.|localStorage|sessionStorage", body)
    # the code is never put in a toast or message
    assert not re.search(r"toast\([^)]*cCode", body)


def test_the_password_and_code_are_cleared_on_close():
    close = _fn("function closeConnect")
    assert 'const p = $("#cPass"); if (p) p.value = "";' in close
    assert '$("#cCode").value = ""' in close
    assert '$("#cCodeRow").style.display = "none"' in close


def test_the_code_is_cleared_on_a_new_login_pick_and_after_every_post():
    assert '$("#cCode").value = ""' in _fn("function pickLogin")
    body = _fn("async function doConnect")
    assert re.search(r'try \{ r = await post\("/api/connect", body\); \}\s*finally \{ if \(code\) \$\("#cCode"\)\.value = ""; \}', body)


def test_step_3_shows_a_tsx_row_as_practice_or_funded():
    assert 'const tsxKind = (a) => a.practice === undefined ? "" : a.practice ? "demo" : "funded";' in BOOK
    assert "vestKind(a) || tsxKind(a) ||" in _fn("function renderAcctList")
