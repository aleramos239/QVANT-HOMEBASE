"""The AlphaTrader option in the Desk's add-account wizard (static files only: no browser, no network)."""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "homebase" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
BOOK = (STATIC / "desk" / "book.js").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    a = BOOK.index(name)
    return BOOK[a:BOOK.index("\n}\n", a)]


def test_step_1_offers_alphatrader():
    assert '<div class="opt" id="optAtr" onclick="wizBroker(\'atr\')">' in INDEX
    opt = INDEX[INDEX.index('id="optAtr"'):INDEX.index('id="optPaper"')]
    assert '<span class="glyph">At</span>' in opt and "AlphaTrader" in opt and "Alpha Futures · email &amp; password" in opt
    # same shape as the TopstepX option: glyph, title + sub, spacer, radio
    tsx = INDEX[INDEX.index('id="optTsx"'):INDEX.index('id="optAtr"')]
    shape = lambda s: re.sub(r"<span class=\"(glyph|t|sub)\">[^<]*</span>", r'<span class="\1">_</span>', s.split(">", 1)[1])
    assert shape(opt.rsplit("<div", 1)[0]) == shape(tsx.rsplit("<div", 1)[0])
    # step 2: the user field is relabelled Email, the code row says which broker sent the code
    assert 'id="cUserLbl"' in INDEX and 'id="cCodeLbl"' in INDEX
    assert 'book.js?v=14' in INDEX


def test_the_env_switch_is_hidden_for_atr():
    assert 'WIZ.broker = b === "vest" ? "vest" : b === "tsx" ? "tsx" : b === "atr" ? "atr" : "tv";' in BOOK
    assert '$("#optAtr").classList.toggle("sel", WIZ.broker === "atr");' in BOOK
    assert 'setEnv(WIZ.broker === "tv" ? "demo" : WIZ.broker);' in BOOK
    assert '$("#envSeg").style.display = env === "vest" || env === "tsx" || env === "atr" ? "none" : "";' in BOOK
    assert "An AlphaTrader login lists every Alpha account under it. Nothing trades until you assign it to a strategy." in BOOK
    assert "Log in to AlphaTrader" in BOOK
    assert '"Email"' in _fn("function wizBroker") and "Code from AlphaTrader" in _fn("function wizBroker")
    assert 'l.env === "atr" ? "AlphaTrader"' in BOOK                          # a saved atr: login is labelled in words


def test_doConnect_sends_broker_atr_and_the_code():
    body = _fn("async function doConnect")
    assert 'broker: "atr"' in body and "username: $(\"#cUser\").value" in body and "code" in body
    assert 'WIZ.broker === "atr"' in body
    assert "r.needs_code" in body and "AlphaTrader sent you a code — type it in" in body
    assert 'codeRow.style.display = ""' in body and "$(\"#cCode\").focus()" in body
    assert "{saved_key: WIZ.saved, ...withCode}" in body
    assert not re.search(r"console\.|localStorage|sessionStorage", body)
    assert not re.search(r"toast\([^)]*cCode", body)


def test_the_password_and_code_are_cleared_on_close():
    close = _fn("function closeConnect")
    assert 'const p = $("#cPass"); if (p) p.value = "";' in close
    assert '$("#cCode").value = ""' in close
    assert '$("#cCodeRow").style.display = "none"' in close


def test_step_3_shows_an_atr_row_as_practice_or_funded():
    # the rows carry practice true/false; the same kind label serves TopstepX and AlphaTrader
    assert 'const tsxKind = (a) => a.practice === undefined ? "" : a.practice ? "practice" : "funded";' in BOOK
    assert "vestKind(a) || tsxKind(a) ||" in _fn("function renderAcctList")
