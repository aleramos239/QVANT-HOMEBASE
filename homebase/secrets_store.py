"""Credential storage — a local file in the app's state dir (not the Keychain).

Originally backed by the macOS Keychain via ``keyring``, but the Keychain ties
"Always Allow" to one exact binary, so every rebuild produced a fresh unsigned
binary the Keychain didn't recognize and re-prompted for permission. Secrets now
live in a single JSON file (``state_dir/credentials.json``, chmod 600) next to
the token cache that already sits there — so there is no Keychain involved and
nothing to prompt about, across any number of rebuilds.

Migration is automatic and one-shot: on a miss we read the value the old build
left in the Keychain ONCE, write it to the file, and never touch the Keychain
again — so existing logins keep working without re-entry (one final macOS
permission click and it's done).

Each account references a ``keyring_key``; the value stored is a small dict,
e.g. {"username": ..., "password": ...}.

    python -m onyx.secrets_store set tv-main
    python -m onyx.secrets_store check tv-main
    python -m onyx.secrets_store delete tv-main
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .paths import state_dir

# Legacy macOS Keychain service name — kept only so we can migrate values the
# old Keychain-backed builds stored, then leave the Keychain alone for good.
SERVICE = "onyx"


def _store_path() -> Path:
    return state_dir() / "credentials.json"


def _load_all() -> dict:
    p = _store_path()
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_all(data: dict) -> None:
    """Write the store atomically with owner-only (0600) permissions."""
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    for f in (tmp, p):
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    tmp.replace(p)
    try:
        os.chmod(p, 0o600)   # ensure the final file is locked down too
    except OSError:
        pass


def _migrate_from_keychain(keyring_key: str) -> Optional[dict]:
    """One-shot: pull a credential a Keychain-backed build left behind and
    persist it to the file, so the next read (and every read after) hits the
    file and never the Keychain. Returns the blob if migrated, else None.
    Best-effort — if ``keyring`` is unavailable or the read fails, returns None.
    """
    try:
        import keyring   # lazy: the file store has no hard dependency on it
        raw = keyring.get_password(SERVICE, keyring_key)
    except Exception:     # noqa: BLE001 — keyring missing / access denied / etc.
        return None
    if not raw:
        return None
    try:
        blob = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if isinstance(blob, dict):
        set_credentials(keyring_key, **blob)
        return blob
    return None


def get_credentials(keyring_key: str) -> Optional[dict]:
    """Return the stored credential dict, or None if absent. Transparently
    migrates a legacy Keychain entry to the file on first access."""
    if not keyring_key:
        return None
    blob = _load_all().get(keyring_key)
    if blob is not None:
        return blob
    return _migrate_from_keychain(keyring_key)


def set_credentials(keyring_key: str, **fields) -> None:
    """Store a credential dict (e.g. username=..., password=...) under keyring_key."""
    if not keyring_key:
        return
    data = _load_all()
    data[keyring_key] = fields
    _save_all(data)


def delete_credentials(keyring_key: str) -> None:
    data = _load_all()
    if keyring_key in data:
        data.pop(keyring_key, None)
        _save_all(data)
    # Best-effort: also clear any leftover legacy Keychain entry.
    try:
        import keyring
        keyring.delete_password(SERVICE, keyring_key)
    except Exception:    # noqa: BLE001 — nothing there / no keyring / denied
        pass


def _cli() -> None:
    import getpass
    import sys

    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "set":
        key = args[1]
        username = input("Tradovate username: ").strip()
        password = getpass.getpass("Tradovate password: ")
        set_credentials(key, username=username, password=password)
        print(f"stored credentials at {_store_path()} under key={key!r}")
    elif len(args) >= 2 and args[0] == "delete":
        delete_credentials(args[1])
        print(f"deleted {args[1]!r}")
    elif len(args) >= 2 and args[0] == "check":
        creds = get_credentials(args[1])
        ok = bool(creds and creds.get("username") and creds.get("password"))
        print(f"{args[1]!r}: {'present' if ok else 'MISSING'}"
              + (f" (username={creds.get('username')})" if ok else ""))
    elif len(args) >= 1 and args[0] == "list":
        keys = sorted(_load_all().keys())
        print("\n".join(keys) if keys else "(no stored credentials)")
    else:
        print("usage:")
        print("  python -m onyx.secrets_store set <keyring_key>")
        print("  python -m onyx.secrets_store check <keyring_key>")
        print("  python -m onyx.secrets_store list")
        print("  python -m onyx.secrets_store delete <keyring_key>")


if __name__ == "__main__":
    _cli()
