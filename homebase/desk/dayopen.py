"""Each account's balance at the start of the Desk day (18:00 ET), for the day's P&L: balance now - balance then.

A broker's own "realized" is no day figure (a paper book's is lifetime, Tradovate's resets on its own clock), and `day.closed_net`
counts only the Desk's strategy trades, so the page reads the balance itself. The file is given by its caller (state_dir() /
"day_open.json"): {account: {"day": the Desk day, "bal": the first balance seen that day}}. The desk's minute loop notes the balance;
the open is the balance the account closed the day before with (equity.jsonl), else the first note of the day: an account with no
history, started mid-day, reads that one day short.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.jsonio import read_dict, write_json


def prior_close(by_day: dict, day: str) -> Optional[float]:
    """The last balance recorded on a date before the Desk day `day` (equity.equity_by_day's {date: balance}): what the
    account held when the day opened, so a desk (re)started mid-day still reads the whole day."""
    before = [d for d in by_day if d < day]
    return by_day[max(before)] if before else None


def note(path: Path, account: str, balance, day: str, prior: Optional[float] = None) -> None:
    """Keep the account's open for `day`: `prior` (the balance it closed the day before with) when known, else the first
    balance seen. An open written without `prior` is replaced once by it; after that a later note changes nothing."""
    if balance is None or not day:
        return
    d = read_dict(path)
    cur = d.get(account) or {}
    if cur.get("day") == day and (cur.get("seeded") or prior is None):
        return
    d[account] = {"day": day, "bal": float(balance if prior is None else prior), **({"seeded": True} if prior is not None else {})}
    write_json(path, d)


def day_pnl(path: Path, account: str, balance, day: str) -> Optional[float]:
    """Balance now minus the day's opening balance; None without a balance or an open for `day`."""
    o = read_dict(path).get(account) or {}
    if balance is None or o.get("day") != day or o.get("bal") is None:
        return None
    return round(float(balance) - float(o["bal"]), 2)
