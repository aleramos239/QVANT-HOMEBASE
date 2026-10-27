"""The desk's daily balance record: equity.jsonl, one line per account per day the balance changed.

Every reader keeps a day's LAST value, so a repeated line adds nothing. The file is given by its caller
(the desk server passes state_dir() / "equity.jsonl"): this module knows no path of its own, which is what
lets a test write and read a file under tmp_path and lets the Engine take equity_by_day as its balance_history.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

_LAST: dict[tuple, tuple] = {}     # (file, account) -> the (date, equity) of its last line
# the file parsed and the stamp it was parsed at; "text": its whole lines parsed into "base" (the last line,
# if it has no newline yet, is folded into a copy and read again next time)
_DAYS: dict = {"stamp": None, "days": {}, "text": "", "base": {}}
_DAYS_LOCK = threading.Lock()


def record_equity(path: Path, account: str, equity: float, date: str) -> None:
    """One line when the account's balance or the date differs from its last line."""
    if _LAST.get((str(path), account)) == (date, equity):
        return
    with open(path, "a") as f:
        f.write(json.dumps({"date": date, "account": account, "equity": equity}) + "\n")
    _LAST[(str(path), account)] = (date, equity)


def _fold(days: dict, text: str) -> dict:
    """The lines of `text` into days, in file order: a day keeps its last value."""
    for line in text.splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("equity") is not None:
            days.setdefault(r.get("account"), {})[r["date"]] = float(r["equity"])
    return days


def _days(path: Path) -> dict[str, dict[str, float]]:
    """equity.jsonl as {account: {date: that day's last equity}}: read again only when the file's stamp
    (inode, size, mtime) has changed, and then only the lines after the ones already parsed are parsed --
    when the file still starts with exactly those lines (it only grew); else every line, from the start."""
    try:
        st = path.stat()
    except OSError:
        return {}
    stamp = (str(path), st.st_ino, st.st_size, st.st_mtime_ns)
    with _DAYS_LOCK:
        if stamp != _DAYS["stamp"]:
            text = path.read_text()
            done = text.rfind("\n") + 1                   # the whole lines; after them a line still being written
            seen, base = _DAYS["text"], _DAYS["base"]
            if not text.startswith(seen):                 # rewritten, shrunk or another file: from the start
                seen, base = "", {}
            # copies (~300 days): a dict handed out never changes, and a line that raises leaves the cache as it was
            base = _fold({a: dict(d) for a, d in base.items()}, text[len(seen):done])
            days = _fold({a: dict(d) for a, d in base.items()}, text[done:]) if done < len(text) else base
            _DAYS.update(stamp=stamp, days=days, text=text[:done], base=base)
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
