"""The desk's daily balance record: equity.jsonl, one line per account per day the balance changed.

Every reader keeps a day's LAST value, so a repeated line adds nothing. The file is given by its caller
(the desk server passes state_dir() / "equity.jsonl"): this module knows no path of its own, which is what
lets a test write and read a file under tmp_path and lets the Engine take equity_by_day as its balance_history.
"""
from __future__ import annotations

import json
from pathlib import Path

_LAST: dict[tuple, tuple] = {}     # (file, account) -> the (date, equity) of its last line
_DAYS: dict = {"stamp": None, "days": {}}   # the file parsed, and the stamp it was parsed at


def record_equity(path: Path, account: str, equity: float, date: str) -> None:
    """One line when the account's balance or the date differs from its last line."""
    if _LAST.get((str(path), account)) == (date, equity):
        return
    with open(path, "a") as f:
        f.write(json.dumps({"date": date, "account": account, "equity": equity}) + "\n")
    _LAST[(str(path), account)] = (date, equity)


def _days(path: Path) -> dict[str, dict[str, float]]:
    """equity.jsonl as {account: {date: that day's last equity}}: parsed once, and again only
    when the file's stamp (inode, size, mtime) has changed."""
    try:
        st = path.stat()
    except OSError:
        return {}
    stamp = (str(path), st.st_ino, st.st_size, st.st_mtime_ns)
    if stamp != _DAYS["stamp"]:
        days: dict[str, dict[str, float]] = {}
        for line in path.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("equity") is not None:
                days.setdefault(r.get("account"), {})[r["date"]] = float(r["equity"])
        _DAYS.update(stamp=stamp, days=days)
    return _DAYS["days"]


def equity_by_day(path: Path, account: str) -> dict[str, float]:
    return dict(sorted(_days(path).get(account, {}).items()))


def daily_pnl(path: Path, account: str, month: str) -> dict:
    """{"days": {date: close-over-close P&L for the month}, "total": their sum}."""
    eq = equity_by_day(path, account)
    days, prev, total = {}, None, 0.0
    for date, e in eq.items():
        if prev is not None and date.startswith(month):
            pnl = round(e - prev, 2)
            days[date] = pnl
            total += pnl
        prev = e
    return {"days": days, "total": round(total, 2)}
