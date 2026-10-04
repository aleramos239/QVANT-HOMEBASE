"""Family registry of the Stage A screen (NQ Level-2 pilot). Contract for family authors: families/README.md.

    REGISTRY = {name: (StrategyClass, default_inputs, both_sides, notes)}

A family author adds ONE module to this directory (one file per family group, e.g. `b_imbalance.py`, `f_flow.py`,
`o_open.py`) that defines

    FAMILIES = {"bimb_follow": (BimbFollow, {}, False, "B1: |z(imb10)| >= 2 at a tf close -> follow"), ...}

Importing this package imports every module in the directory (names not starting with '_'), checks each entry against
the contract (`check_entry`) and merges it into REGISTRY. A module that fails to import, or an entry that breaks the
contract, is NOT registered: it is listed in ERRORS = {module or family name: reason}; `screen.py` refuses to run and
tests/test_families.py fails while ERRORS is not empty (one author's broken file never hides the other families).

Nothing here runs a strategy: no trade, no P&L. `python -m families` prints the registry.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
L = HERE.parent
if str(L) not in sys.path:
    sys.path.insert(0, str(L))

import l2sim  # noqa: E402

TFS = ("1", "5", "15", "30")                       # l2sim.Template's tf choices; the SPEC's screen cadence is 1 and 5
RUN_KEYS = ("strict_limit",)                       # the only execution option a family may pin for the screen (SPEC: B4)
REGISTRY: dict = {}                                # name -> (StrategyClass, default_inputs, both_sides, notes)
MODULE_OF: dict = {}                               # name -> module that registered it
ERRORS: dict = {}                                  # module / family name -> why it is not registered


def feature_columns() -> dict:
    """Columns a family may name in FEATURES -> tier: 'feature' (book / flow: shuffled by the C2 null), 'fixed' (prices,
    anchors, clock tags, flags: the receiving session's own under C2), 'research' (vendor slots: never in the screen)."""
    import l2data as D
    out = {c: "feature" for c in D.BOOK_COLS + D.FLOW_COLS}
    out.update({c: "fixed" for c in D.PX_COLS + ["f_o", "f_h", "f_l", "f_c", "t_utc", "et_min"] + D.FLAG_COLS})
    out.update({c: "research" for c in D.RT_COLS})
    return out


def check_entry(name: str, entry) -> list:
    """Contract violations of one registry entry (empty list = fine). Static checks only: nothing is run."""
    bad = []
    if not (isinstance(name, str) and name and name.replace("_", "").isalnum() and name == name.lower()):
        bad.append(f"name {name!r}: lower-case letters, digits and '_' only (it becomes the run key)")
    if not (isinstance(entry, tuple) and len(entry) == 4):
        return bad + ["entry must be the 4-tuple (StrategyClass, default_inputs, both_sides, notes)"]
    cls, inputs, both, notes = entry
    if not (isinstance(cls, type) and issubclass(cls, l2sim.Template)):
        return bad + ["StrategyClass must subclass l2sim.Template"]
    if not isinstance(inputs, dict):
        return bad + ["default_inputs must be a dict (overrides of the class DEFAULTS; {} = the class defaults)"]
    if not isinstance(both, bool):
        bad.append("both_sides must be True (the family rests entry orders on both sides: OCO / two legs) or False")
    if not (isinstance(notes, str) and notes.strip()):
        bad.append("notes must be a non-empty string (SPEC id + one line: trigger, and 'REVISIT' where the SPEC says so)")
    if "tf" in inputs or inputs.get("sess", "all") != "all":
        bad.append("default_inputs must not set tf (the screen runs every tf of SCREEN_TFS) or a sess other than 'all'")
    try:
        probe = cls({**inputs, "tf": "5"})
    except Exception as e:                           # noqa: BLE001 - reported, not raised
        return bad + [f"{cls.__name__}(default_inputs) is refused by resolve_inputs: {type(e).__name__}: {e}"]
    own = {k for c in cls.__mro__ if c not in l2sim.Template.__mro__ for k in c.__dict__.get("DEFAULTS", {})}
    missing = sorted(own - set(cls.schema()))
    if missing:
        bad.append(f"SCHEMA does not declare the family inputs {missing} (choices / ranges for every key of DEFAULTS)")
    if probe.p.get("f_depth", "off") != "off":
        bad.append("f_depth must stay 'off' in the screen (SPEC: B6 is tested as gate G2 only)")
    tfs = getattr(cls, "SCREEN_TFS", None)
    if not (isinstance(tfs, tuple) and tfs and all(t in TFS for t in tfs) and len(set(tfs)) == len(tfs)):
        bad.append(f"class attribute SCREEN_TFS must be a non-empty tuple of distinct tf strings out of {TFS}")
    feats = getattr(cls, "FEATURES", None)
    if not (isinstance(feats, tuple) and feats and all(isinstance(c, str) for c in feats)):
        bad.append("class attribute FEATURES must be a non-empty tuple: EVERY column the family reads through ctx.feat / feat_window")
    else:
        tiers = feature_columns()
        unknown = [c for c in feats if c not in tiers]
        research = [c for c in feats if tiers.get(c) == "research"]
        if unknown:
            bad.append(f"FEATURES names columns the data layer does not have: {unknown} (FEATURES.md)")
        if research:
            bad.append(f"FEATURES holds research-tier columns {research}: not reproducible live, never in the screen")
        if not unknown and not any(tiers[c] == "feature" for c in feats):
            bad.append("FEATURES holds no book / flow feature (only prices / tags / flags): the C2 null has nothing to shuffle")
    kw = getattr(cls, "SCREEN_RUN", {})
    if not isinstance(kw, dict) or set(kw) - set(RUN_KEYS) or any(not isinstance(v, bool) for v in kw.values()):
        bad.append(f"class attribute SCREEN_RUN may only hold {RUN_KEYS} (booleans); slippage / latency are stress, not screen")
    if not isinstance(cls.__dict__.get("session_independent", getattr(cls, "session_independent", None)), bool):
        bad.append("session_independent must be a bool (True only if NO state survives a session)")
    return bad


def load(reload: bool = False) -> dict:
    """(Re)build REGISTRY from every module of this directory. Returns REGISTRY; problems go to ERRORS."""
    REGISTRY.clear()
    MODULE_OF.clear()
    ERRORS.clear()
    for info in sorted(pkgutil.iter_modules([str(HERE)]), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        full = f"{__name__}.{info.name}"
        try:
            mod = importlib.reload(sys.modules[full]) if (reload and full in sys.modules) else importlib.import_module(full)
        except Exception as e:                       # noqa: BLE001 - one broken module must not hide the others
            ERRORS[info.name] = f"import failed: {type(e).__name__}: {e}"
            continue
        fams = getattr(mod, "FAMILIES", None)
        if not isinstance(fams, dict) or not fams:
            ERRORS[info.name] = "module defines no FAMILIES = {name: (StrategyClass, default_inputs, both_sides, notes)}"
            continue
        for name, entry in fams.items():
            bad = check_entry(name, entry)
            if name in REGISTRY:
                bad.append(f"name already registered by families/{MODULE_OF[name]}.py")
            if not bad and entry[0].__module__ != full:
                bad.append(f"{entry[0].__name__} is defined in {entry[0].__module__}, not in this module (workers import it by name)")
            if bad:
                ERRORS[str(name)] = f"families/{info.name}.py: " + "; ".join(bad)
                continue
            REGISTRY[name] = entry
            MODULE_OF[name] = info.name
    return REGISTRY


def columns(name: str) -> tuple:
    """The feature columns of a registered family (its class's FEATURES), for l2sim.L2Features / score.C2Features."""
    return tuple(REGISTRY[name][0].FEATURES)


def screen_inputs(name: str, tf: str) -> dict:
    """The inputs of the family's screen run at one tf: its registered defaults + tf, all sessions."""
    return {**REGISTRY[name][1], "tf": str(tf), "sess": "all"}


load()


def main() -> int:
    for name, (cls, inputs, both, notes) in sorted(REGISTRY.items()):
        print(f"{name:16s} {MODULE_OF[name]}.{cls.__name__:18s} tfs {','.join(cls.SCREEN_TFS):6s} both_sides {both!s:5s} "
              f"inputs {inputs}  features {','.join(cls.FEATURES)}  | {notes}")
    for k, v in ERRORS.items():
        print(f"ERROR {k}: {v}")
    print(f"{len(REGISTRY)} families, {len(ERRORS)} errors")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
