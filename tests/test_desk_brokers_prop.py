from homebase.config import AccountCfg
from homebase.desk_app import brokers


def test_is_prop():
    assert brokers.is_prop(AccountCfg(keyring_key="tradovate:x", account_name="PAAPEX3265980000023"))
    assert not brokers.is_prop(AccountCfg(keyring_key="tradovate:x", account_name="1552885", live=True))
    assert not brokers.is_prop(AccountCfg(account_name="paper-6", paper=True))
    assert not brokers.is_prop(AccountCfg(account_name="PAPER", paper=True, prop={"rules": "x"}))
    assert brokers.is_prop(AccountCfg(keyring_key="tsx:me", account_name="123"))
    assert brokers.is_prop(AccountCfg(keyring_key="tradovate:x", account_name="123", prop={"rules": "lucid"}))
    assert not brokers.is_prop(AccountCfg(keyring_key=None, account_name=None))     # a null in the config never raises
