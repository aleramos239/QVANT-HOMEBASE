"""Each account's balance at the start of the Desk day (18:00 ET), for the day's P&L: balance now - balance then.

A broker's own "realized" is no day figure (a paper book's is lifetime, Tradovate's resets on its own clock), and `day.closed_net`
counts only the Desk's strategy trades, so the page reads the balance itself. The file is given by its caller (state_dir() /
"day_open.json"): {account: {"day": the Desk day, "bal": the first balance seen that day}}. The desk's minute loop notes the balance;
the first note of a day is the open. A desk first started mid-day opens at that first note: that one day reads short.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.jsonio import read_dict, write_json


def note(path: Path, account: str, balance, day: str) -> None:
    """Keep the account's first balance of `day`; a later note of the same day changes nothing."""
    if balance is None or not day:
        return
    d = read_dict(path)
    if (d.get(account) or {}).get("day") == day:
        return
    d[account] = {"day": day, "bal": float(balance)}
    write_json(path, d)


def day_pnl(path: Path, account: str, balance, day: str) -> Optional[float]:
    """Balance now minus the day's opening balance; None without a balance or an open for `day`."""
    o = read_dict(path).get(account) or {}
    if balance is None or o.get("day") != day or o.get("bal") is None:
        return None
    return round(float(balance) - float(o["bal"]), 2)
