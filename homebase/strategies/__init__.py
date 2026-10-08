"""Strategies shared by the Strategy Tester and (later) the desk. See base.py."""
from __future__ import annotations

from .base import Input, Strategy, resolve_inputs
from .gc_nfp import GCNfp
from .gc_nfpcpi import GCNfpCpi
from .nq930 import NQ930

REGISTRY: dict[str, type[Strategy]] = {c.id: c for c in (NQ930, GCNfpCpi, GCNfp)}


def get(strategy_id: str) -> type[Strategy]:
    try:
        return REGISTRY[strategy_id]
    except KeyError:
        raise ValueError(f"unknown strategy {strategy_id!r}") from None


def catalog() -> list[dict]:
    return [c.describe() for c in REGISTRY.values()]


__all__ = ["Input", "Strategy", "resolve_inputs", "REGISTRY", "get", "catalog"]
