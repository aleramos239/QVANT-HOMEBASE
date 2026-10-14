"""pay_rules.py -- the payout pipeline's numbers for THE SET, as data: templates/payout.json. None is typed in code.

  need(*keys)        one number, or one level, of payout.json (a copy); a key it does not have: rules.RuleError
  slots()            [{"id", "label", "from", "to", "lo", "hi"}] in the day's order; lo / hi = minutes from the evening's start
                     (18:00 New York, the futures day's first minute), so a slot that ends at midnight is a plain range
  slot_of(minute)    the slot a clock minute of the day (0 .. 1439, New York) falls in, or None
  firm(rule_id)      "lucid" | "apex" | ... : the word a rule file's id starts with, and its numbers of `firms` (firm_need)
  after(rule_id)     what happens after a payout for this rule file (`after_payout`, the longest start that fits), or {}
Standard library only. Locked by tests/test_pay_score.py.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache

from . import rules as R

FILE = R.T / "payout.json"
DAY0 = 18 * 60                                      # the futures day starts at 18:00 New York


@lru_cache(maxsize=None)
def _load(path: str, stamp: int) -> dict:
    return {k: v for k, v in json.loads(open(path, encoding="utf-8").read()).items() if not k.startswith("_")}


def _all() -> dict:
    return _load(str(FILE), FILE.stat().st_mtime_ns)


def need(*keys):
    d = _all()
    for i, k in enumerate(keys):
        if not isinstance(d, dict) or k not in d:
            raise R.RuleError(f"payout.json has no {'.'.join(str(x) for x in keys[:i + 1])}")
        d = d[k]
    return copy.deepcopy(d)


def _clock(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _since(minute: int) -> int:
    """Minutes since the futures day's start (18:00) for a clock minute of the day."""
    return (minute - DAY0) % 1440


def slots() -> list:
    out = []
    for s in need("slots"):
        lo, hi = _since(_clock(s["from"])), _since(_clock(s["to"]))
        out.append({**s, "lo": lo, "hi": hi if hi > lo else hi + 1440})
    return sorted(out, key=lambda s: s["lo"])


def slot_of(minute: int):
    m = _since(int(minute))
    return next((s["id"] for s in slots() if s["lo"] <= m < s["hi"]), None)


def firm(rule_id: str) -> str:
    return str(rule_id).split("-", 1)[0]


def firm_need(rule_id: str) -> dict:
    return need("firms").get(firm(rule_id)) or {}


def after(rule_id: str) -> dict:
    fits = [k for k in need("after_payout") if str(rule_id).startswith(k)]
    return need("after_payout", max(fits, key=len)) if fits else {}
