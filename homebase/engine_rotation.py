"""Account rotation for the built-in kinds (the owner, 2026-10-19; off by default): one account a trade, taking turns.

Engine (engine.py) inherits RotationMixin; the methods moved here from engine.py unchanged. They read the Engine's cfg,
adapters, _root, account_locked, _slot_busy and journal, and own self.rotation (set in Engine.__init__, kept in
<state>/rotation.json across days)."""
from __future__ import annotations

import json
import sys
from typing import Optional

from .config import StrategyCfg, assignments
from .engine_lab import LAB_ACCOUNT_STOPPED, LAB_NOT_CONNECTED, LAB_SLOT_BUSY

ROTATION_NONE = "No booked account could take this trade."


class RotationMixin:
    # --- account rotation: one account a trade, taking turns (the owner, 2026-10-19; off by default) -------------
    def _rotation_path(self):
        return self._root / "rotation.json"           # not per day: the turn carries over to the next day

    def _load_rotation(self) -> None:
        p = self._rotation_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            self.rotation = {k: dict(v) for k, v in data.items() if isinstance(v, dict)}
        except Exception as e:  # noqa: BLE001 -- the desk must still start
            print(f"homebase engine: reading {p.name} failed: {e!r}", file=sys.stderr)

    def _save_rotation(self) -> None:
        p = self._rotation_path()
        tmp = p.with_suffix(".tmp")                   # never half a file: a lost switch would trade every account
        tmp.write_text(json.dumps(self.rotation, indent=2) + "\n")
        tmp.replace(p)

    def rotating(self, name: str) -> bool:
        return bool(self.rotation.get(name, {}).get("on"))

    def _turn_order(self, name: str) -> list[str]:
        """The booked accounts in book order, starting after the one that took the last trade (wrapping); from the
        first when that account is no longer booked."""
        book = list(dict.fromkeys(a["account"] for a in assignments(self.cfg, name)))
        last = self.rotation.get(name, {}).get("last")
        i = book.index(last) + 1 if last in book else 0
        return book[i:] + book[:i]

    def rotation_view(self, name: str) -> dict:
        on = self.rotating(name)
        order = self._turn_order(name) if on else []
        return {"on": on, "next": order[0] if order else None}

    def set_rotation(self, name: str, on: bool) -> dict:
        self.rotation.setdefault(name, {})["on"] = bool(on)
        self._save_rotation()
        self.journal("rotation_set", strategy=name, on=bool(on))
        return self.rotation_view(name)

    def _turn_taken(self, name: str, account: str) -> None:
        self.rotation.setdefault(name, {})["last"] = account
        self._save_rotation()

    def _no_turn(self, name: str, skipped: dict) -> None:
        self.journal("rotation_skipped", strategy=name, reason=ROTATION_NONE, accounts=skipped)

    def _one_turn(self, name: str, cfg: StrategyCfg, accounts: list) -> Optional[str]:
        """A built-in's trade with rotation on: of `accounts` (still in play), the first in turn that can take it now
        -- _place / _place_one's own checks, without their side effects -- and the turn moves to it. None: none can
        (journaled once)."""
        skipped = {}
        for a in self._turn_order(name):
            if a not in accounts:
                continue
            ad = self.adapters.get(a)
            why = (LAB_ACCOUNT_STOPPED if self.account_locked(a)
                   else LAB_NOT_CONNECTED if ad is None or not ad.connected
                   else LAB_SLOT_BUSY if self._slot_busy(name, cfg, a, lab_only=True) else None)
            if why is None:
                self._turn_taken(name, a)
                return a
            skipped[a] = why
        self._no_turn(name, skipped)
        return None
