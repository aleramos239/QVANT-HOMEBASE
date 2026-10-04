"""Pilot selector shared by the research scripts (NQ is the default; nothing changes unless PP_PILOT is set).

  PP_PILOT=es            -> root ES, pilot dir ../2026-09-30-es, drafts pp_es_<fam> (ids draft_pp_es_<fam>)
  --pilot es / --dir D on the command line do the same as the env vars (PP_PILOT / PP_DIR)
  PP_ROOT=ES PP_DIR=...  -> override the root / pilot directory (PP_DIR may be any path)
Code (template.py, families/, *.py) always lives in this directory (CODE); a pilot's DATA (ledger.csv, jobs.jsonl,
queue.jsonl, out/, bundles_cache/, progress.md, family_inputs.json, ...) lives in DIR (= CODE for NQ).
shared(name) = DIR/name if it exists, else CODE/name (news_days.csv, fees.json, family_inputs.json).
Dollar constants come from homebase.contracts (ES $50/pt, MES $5/pt, tick 0.25): PV = $/pt of ONE full contract,
PV_MICRO = PV/10, TICK_USD = 1 tick on ONE micro (NQ $0.50, ES $1.25), TICK_FULL = 1 tick on one full contract.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent
REPO = CODE.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from homebase.contracts import point_value, tick_size   # noqa: E402

PILOTS = {"nq": dict(root="NQ", dir=CODE), "es": dict(root="ES", dir=CODE.parent / "2026-09-30-es")}


def _flag(flag: str) -> str | None:
    """--flag value / --flag=value anywhere in sys.argv (lets every script take --pilot es without its own argparse)."""
    a = sys.argv
    for i, x in enumerate(a):
        if x == flag and i + 1 < len(a):
            return a[i + 1]
        if x.startswith(flag + "="):
            return x.split("=", 1)[1]
    return None


def strip_flags(argv: list) -> list:
    out, skip = [], False
    for x in argv:
        if skip:
            skip = False
        elif x in ("--pilot", "--dir"):
            skip = True
        elif not x.startswith(("--pilot=", "--dir=")):
            out.append(x)
    return out


def select(name: str | None = None, root: str | None = None, dir_: str | os.PathLike | None = None) -> dict:
    name = (name or _flag("--pilot") or os.environ.get("PP_PILOT") or "nq").lower()
    base = PILOTS.get(name) or dict(root=name.upper(), dir=CODE.parent / f"pilot-{name}")
    root = (root or os.environ.get("PP_ROOT") or base["root"]).upper()
    d = Path(dir_ or _flag("--dir") or os.environ.get("PP_DIR") or base["dir"]).expanduser().resolve()
    pv, tk = float(point_value(root)), float(tick_size(root))
    return dict(name=name, root=root, dir=d, prefix="pp_" if name == "nq" else f"pp_{name}_", pv=pv, tick=tk,
                pv_micro=pv / 10.0, tick_usd=tk * pv / 10.0, tick_full=tk * pv)


_P = select()
sys.argv[1:] = strip_flags(sys.argv[1:])        # scripts with their own argparse never see --pilot / --dir
NAME, ROOT, DIR, PREFIX = _P["name"], _P["root"], _P["dir"], _P["prefix"]
PV, TICK, PV_MICRO, TICK_USD, TICK_FULL = _P["pv"], _P["tick"], _P["pv_micro"], _P["tick_usd"], _P["tick_full"]


def shared(name: str) -> Path:
    p = DIR / name
    return p if p.exists() else CODE / name
