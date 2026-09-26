"""A pinned account that is not on the login is an ERROR, never a fallback
(2026-09-26: pins ...044/...045 silently connected to ...047)."""
from __future__ import annotations

import pytest

from tests.test_tradovate import mkadapter, tradovate_like

ACCTS = [{"id": 47, "name": "APEX-047", "active": True},
         {"id": 48, "name": "APEX-048", "active": True}]


def test_a_pinned_name_missing_from_the_login_raises_and_disconnects(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)          # connected, on account 66121477
    ad.account_selector = {"account_name": "APEX-044"}
    with pytest.raises(RuntimeError,
                       match=r"^account APEX-044 not on this login \(has: APEX-047, APEX-048\)$"):
        ad._resolve_account(ACCTS)
    assert (ad._acct_num, ad._acct_name, ad.pinned_ok) == (None, "", False)
    assert ad.connected is False                        # never "connected" on the wrong account


def test_a_pinned_id_missing_raises_too(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad.account_selector = {"tradovate_account_id": 44}
    with pytest.raises(RuntimeError, match=r"^account 44 not on this login"):
        ad._resolve_account(ACCTS)


def test_a_pin_matches_by_name_or_nickname_case_insensitively(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad.account_selector = {"account_name": "my eval"}
    ad._resolve_account([ACCTS[0], {"id": 48, "name": "APEX-048", "nickname": "My Eval"}])
    assert (ad._acct_num, ad._acct_name, ad.pinned_ok) == (48, "APEX-048", True)


def test_no_pin_keeps_the_first_active_fallback_but_is_not_pinned(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad.account_selector = {}
    ad._resolve_account([{"id": 47, "name": "APEX-047", "active": False}, ACCTS[1]])
    assert (ad._acct_num, ad._acct_name, ad.pinned_ok) == (48, "APEX-048", False)
