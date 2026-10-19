"""App-wide settings for the charts page (Task 4, 2026-09-27
accounts-paper-layouts-appsettings plan): `.state/charts/settings.json`.

Today this is just the market-data login choice ("live" | "demo"). More
app-wide settings (the plan says "structured so more can be added later")
land in the same file as more keys; each getter/setter here owns one key so
a partial file (an old version, a crash mid-write) never loses the others.

HOMEBASE_CHARTS_MD (homebase.charts.MD_ENV) is the default `md` when the
file has no choice yet -- so today's behaviour is unchanged until the user
picks one in the Settings dialog, exactly like the brief asks.

HOMEBASE_CHARTS_MD_ONLY pins the login on a machine that must never take the other one, whatever the
file or the dialog say, and keeps the second socket (md_other_roots) shut. The server runs "demo"
(2026-10-19): Tradovate gives the live login's market data to ONE connection at a time, and the server's
charts and the Mac's kicked each other off every ~5 minutes, leaving holes in both.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import MD_ENV

MD_CHOICES = ("live", "demo")
CLOCK_CHOICES = ("12h", "24h")      # how every page prints a time of day; the first is the default


def md_only() -> str | None:
    """HOMEBASE_CHARTS_MD_ONLY: the one login this machine's charts may use, or None (any)."""
    v = os.environ.get("HOMEBASE_CHARTS_MD_ONLY", "").strip().lower()
    return v if v in MD_CHOICES else None


class SettingsStore:
    """One JSON file, atomic writes (temp file + rename, like layouts.json /
    templates.json elsewhere in this package): a crash or a full disk
    mid-write must never tear the file."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _read(self) -> dict:
        try:
            v = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}

    def _write(self, data: dict) -> None:
        """Temp file + fsync + atomic rename (review M6): a crash or a full disk mid-write must
        never tear the file, and the rename must never land ahead of the data actually reaching
        disk -- a full disk here raises (OSError), and the caller (server.py's PUT /api/settings)
        rolls the feed itself back rather than leaving it switched with a stale file underneath."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "w") as f:
            f.write(json.dumps(data, indent=2))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def get(self) -> dict:
        """{"md": "live"|"demo"} -- MD_ENV when the file has none yet or its
        value is not one of MD_CHOICES (a hand-edited or stale file)."""
        d = self._read()
        md = md_only() or d.get("md")
        if md not in MD_CHOICES:
            md = MD_ENV
        return {"md": md}

    def other_roots(self) -> list[str]:
        """"md_other_roots": the markets that ride the OTHER login's md socket (the one `md` does
        not name), e.g. ["YM", "GC", "SI"] when only the eval logins carry CBOT / COMEX. Read at
        start-up; [] (one socket for everything) unless the file holds a list of names."""
        v = self._read().get("md_other_roots")
        if not isinstance(v, list) or md_only():
            return []
        return list(dict.fromkeys(x.upper() for x in v if isinstance(x, str) and x.strip()))

    def set_md(self, md: str) -> dict:
        if md not in MD_CHOICES:
            raise ValueError(f"md must be one of {MD_CHOICES}")
        if md_only() not in (None, md):
            raise ValueError(f"this machine's charts use the {md_only()} login only (HOMEBASE_CHARTS_MD_ONLY)")
        d = self._read()
        d["md"] = md
        self._write(d)
        return self.get()

    def clock(self) -> str:
        """"12h" | "24h": the one clock format of the Desk, Charts and Lab pages (static/hbclock.js)."""
        v = self._read().get("clock")
        return v if v in CLOCK_CHOICES else CLOCK_CHOICES[0]

    def set_clock(self, clock: str) -> str:
        if clock not in CLOCK_CHOICES:
            raise ValueError(f"clock must be one of {CLOCK_CHOICES}")
        d = self._read()
        d["clock"] = clock
        self._write(d)
        return clock
