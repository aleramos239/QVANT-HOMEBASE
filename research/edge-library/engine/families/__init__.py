"""Family registry. Contract for family authors: ../ENGINE.md (edge library) and families/README.md (the L2 pilot's screen).

    REGISTRY = {name: (StrategyClass, default_inputs, both_sides, notes)}
    LIBRARY  = {name: {"rationale", "complexity", "variants", "roots", "l2", "weak", ...}}     (EDGE LIBRARY entries)

EDGE LIBRARY ENTRY = a 5-tuple: the four fields above + a dict
    {"rationale": "<ONE sentence, written before any test: who is on the other side / what flow it rides / why it persists>",
     "complexity": <int: rules + free parameters of the family>,                                  # both MANDATORY
     "variants": [{"n": 10}, {"n": 20}, ...],     # the family-parameter variants (EDGE_SPEC "PROPER RE-RUN" 4); default [{}]
     "roots": ("NQ", "ES", "GC"),                 # default: all three for a family without features, ("NQ",) with features
     "weak": False,                               # True = WEAK RATIONALE / WEAK PRIOR (admission needs t >= 3 on BUILD)
     "ported": "donchian",                        # the R family it ports (it then needs a tester-match gate), else omit
     "penalty": "..."}                            # EDGE_SPEC C: a favourite that failed on 2025-26 (text for the card)
A family that reads no Level-2 feature sets FEATURES = () on its class. A 4-tuple (the L2 pilot's screen families) stays
registered in REGISTRY but is NOT a library family: run_menus refuses it until it carries a rationale and a complexity.

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
LIBRARY: dict = {}                                 # name -> edge-library meta (rationale, complexity, variants, roots, ...)
MODULE_OF: dict = {}                               # name -> module that registered it
ERRORS: dict = {}                                  # module / family name -> why it is not registered
LIB_KEYS = ("rationale", "complexity", "variants", "roots", "weak", "ported", "penalty")
L2_OPTIONS = ("f_depth", "f_book", "x_book", "f_thin")      # Template L2 options: off in every base entry (EDGE_SPEC D2-D4:
#                                                             tested only on base units that pass the BUILD plateau)

# ---- EDGE_SPEC "ORCHESTRATOR DECISIONS 2026-10-03" (taken P&L-blind, BEFORE any valid run; they bind every later stage) ----
# Laid over the authors' entries by load(): ONE place, no author module is edited. LIBRARY[name] gains
#   weak          True also for the names below (decision 4)
#   mirror        the variant axis whose values are OPPOSITE hypotheses: each value is its own plateau unit (decision 2)
#   penalty_sess  the sessions the family's failure penalty applies to (None = every session; decision 4)
#   second_look   the EDGE_SPEC rule-3 label for the card, or None        notes   the registry notes (+ CARD_NOTES)
WEAK_FAMILIES = ("straddle_t_0000", "straddle_t_1105",                       # no event behind the time
                 "tod_drift", "vwap_ema_x",                                  # no counterparty / a weak prior
                 "ema_ribbon", "tema_slope", "ema_pullback", "supertrend")   # the rationale only restates the trigger
MIRROR = {"tod_drift": "dir", "ib": "mode", "gap": "mode",                   # long vs short . break vs fade . fill vs go
          "orb_confirm": "dir"}                                             # STAGE 2b N3: long-only vs short-only units
PENALTY_SESS = {"donchian": ("pm",)}                                         # donchian: its pm favourite failed; first_bar_mom: all
CARD_NOTES = {"straddle_t_2000": "ORCHESTRATOR DECISION 5: 20:00 ET stays 20:00 ET all year (the user's time); the Tokyo cash "
                                 "open is 19:00 ET in the US winter, so the fire is one hour after it then."}


def check_library(name: str, cls, inputs: dict, lib) -> tuple:
    """Contract violations of an entry's edge-library dict, and its normalised form. -> (problems, meta)."""
    bad = []
    if not isinstance(lib, dict):
        return ["the 5th field must be a dict {'rationale': ..., 'complexity': ..., ...}"], None
    unknown = sorted(set(lib) - set(LIB_KEYS))
    if unknown:
        bad.append(f"unknown library keys {unknown}; allowed {LIB_KEYS}")
    rat = lib.get("rationale")
    if not (isinstance(rat, str) and len(rat.strip()) >= 20):
        bad.append("'rationale' is mandatory: ONE sentence written before any test (who is on the other side / what flow / why it persists)")
    cx = lib.get("complexity")
    if isinstance(cx, bool) or not isinstance(cx, int) or cx < 1:
        bad.append("'complexity' is mandatory: an int >= 1 (rules + free parameters of the family)")
    feats = tuple(getattr(cls, "FEATURES", ()) or ())
    roots = tuple(lib.get("roots") or (("NQ",) if feats else tuple(l2sim.SPECS)))
    if not roots or any(r not in l2sim.SPECS for r in roots) or len(set(roots)) != len(roots):
        bad.append(f"'roots' must be distinct roots out of {tuple(l2sim.SPECS)}")
    elif feats and any(r not in l2sim.L2_ROOTS for r in roots):
        bad.append(f"a family that reads Level-2 features runs on {sorted(l2sim.L2_ROOTS)} only (EDGE_SPEC user rule 4)")
    variants = lib.get("variants") if lib.get("variants") is not None else [{}]
    if not (isinstance(variants, (list, tuple)) and variants and all(isinstance(v, dict) for v in variants)):
        bad.append("'variants' must be a non-empty list of input-override dicts ([{}] = the defaults only)")
        variants = [{}]
    tfs = getattr(cls, "SCREEN_TFS", None) or ("5",)
    ids = set()
    for v in variants:
        clash = sorted(set(v) & {"tf", "sess", "stop_mode", "stop_val", "tgt_r", *L2_OPTIONS})
        if clash:
            bad.append(f"variant {v}: may not set {clash} (tf / sess belong to the unit, the exits to the menu, the L2 options to stage D)")
            continue
        try:
            cls({**inputs, **v, "tf": str(tfs[0])})
        except Exception as e:                       # noqa: BLE001 - reported, not raised
            bad.append(f"variant {v} is refused by resolve_inputs: {type(e).__name__}: {e}")
        vid = l2sim.cell_id(v) if v else ""
        if vid in ids:
            bad.append(f"duplicate variant {v}")
        ids.add(vid)
    for k in ("weak",):
        if k in lib and not isinstance(lib[k], bool):
            bad.append(f"'{k}' must be a bool")
    for k in ("ported", "penalty"):
        if k in lib and not (isinstance(lib[k], str) and lib[k].strip()):
            bad.append(f"'{k}' must be a non-empty string when given")
    meta = {"rationale": (rat or "").strip() if isinstance(rat, str) else "", "complexity": cx, "variants": [dict(v) for v in variants],
            "roots": roots, "l2": bool(feats), "weak": bool(lib.get("weak", False)), "ported": lib.get("ported"),
            "penalty": lib.get("penalty")}
    return bad, meta


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
    if not (isinstance(entry, tuple) and len(entry) in (4, 5)):
        return bad + ["entry must be the tuple (StrategyClass, default_inputs, both_sides, notes[, library dict])"]
    cls, inputs, both, notes = entry[:4]
    lib = len(entry) == 5
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
    tfs0 = getattr(cls, "SCREEN_TFS", None)
    tf0 = str(tfs0[0]) if isinstance(tfs0, tuple) and tfs0 and tfs0[0] in TFS else "5"      # a tf the family itself runs at
    try:
        probe = cls({**inputs, "tf": tf0})
    except Exception as e:                           # noqa: BLE001 - reported, not raised
        return bad + [f"{cls.__name__}(default_inputs) is refused by resolve_inputs: {type(e).__name__}: {e}"]
    own = {k for c in cls.__mro__ if c not in l2sim.Template.__mro__ for k in c.__dict__.get("DEFAULTS", {})}
    missing = sorted(own - set(cls.schema()))
    if missing:
        bad.append(f"SCHEMA does not declare the family inputs {missing} (choices / ranges for every key of DEFAULTS)")
    if probe.p.get("f_depth", "off") != "off":
        bad.append("f_depth must stay 'off' in the screen (SPEC: B6 is tested as gate G2 only)")
    on = [k for k in L2_OPTIONS[1:] if probe.p.get(k, "off") != "off"]
    if on:
        bad.append(f"{on} must stay 'off' in a registry entry (EDGE_SPEC D2-D4: L2 filter / exit variants only on base units "
                   "that pass the BUILD plateau)")
    tfs = getattr(cls, "SCREEN_TFS", None)
    if not (isinstance(tfs, tuple) and tfs and all(t in TFS for t in tfs) and len(set(tfs)) == len(tfs)):
        bad.append(f"class attribute SCREEN_TFS must be a non-empty tuple of distinct tf strings out of {TFS}")
    feats = getattr(cls, "FEATURES", None)
    if lib and feats == ():
        pass                                         # an edge-library family without Level-2 features (NQ / ES / GC)
    elif not (isinstance(feats, tuple) and feats and all(isinstance(c, str) for c in feats)):
        bad.append("class attribute FEATURES must be a non-empty tuple: EVERY column the family reads through ctx.feat / feat_window"
                   + (" (or FEATURES = () for a family that reads none)" if lib else ""))
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
    if lib:
        bad += check_library(name, cls, inputs, entry[4])[0]
    return bad


def load(reload: bool = False) -> dict:
    """(Re)build REGISTRY from every module of this directory. Returns REGISTRY; problems go to ERRORS."""
    REGISTRY.clear()
    LIBRARY.clear()
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
            REGISTRY[name] = tuple(entry[:4])
            MODULE_OF[name] = info.name
            if len(entry) == 5:
                LIBRARY[name] = check_library(name, entry[0], entry[1], entry[4])[1]
                why = _decisions(name)
                if why:
                    ERRORS[str(name)] = f"families/{info.name}.py: {why}"
                    del REGISTRY[name], LIBRARY[name], MODULE_OF[name]
    for name in sorted(set(WEAK_FAMILIES) | set(MIRROR) | set(PENALTY_SESS) | set(CARD_NOTES)):
        if name not in LIBRARY and name not in ERRORS:
            ERRORS[name] = "named in the ORCHESTRATOR DECISIONS overlay (families/__init__.py) but not registered as a library family"
    return REGISTRY


def _decisions(name: str):
    """Lay the ORCHESTRATOR DECISIONS over LIBRARY[name] (see the constants). -> an error text, or None."""
    lib = LIBRARY[name]
    lib["weak"] = bool(lib["weak"] or name in WEAK_FAMILIES)
    axis = MIRROR.get(name)
    if axis is not None and len({str(v.get(axis)) for v in lib["variants"]}) < 2 or any(axis is not None and axis not in v
                                                                                         for v in lib["variants"]):
        return f"MIRROR axis {axis!r} must be set, with >= 2 values, by every variant"
    lib["mirror"] = axis
    ps = PENALTY_SESS.get(name)
    if ps is not None and not lib["penalty"]:
        return "PENALTY_SESS names a family that carries no penalty"
    lib["penalty_sess"] = None if ps is None else tuple(ps)
    lib["notes"] = " ".join(x for x in (REGISTRY[name][3].strip(), CARD_NOTES.get(name, "")) if x)
    lib["second_look"] = second_look(name)
    return None


def second_look(name: str):
    """The SECOND-LOOK label of a family (EDGE_SPEC user rule 3: 2025-26 was already seen once -> the EXAM is a second look
    and the card must say so), or None: the module's own second_look(name) when it defines one (port2, l2ideas), else the
    sentence(s) of the registry notes from the words 'second look' on (port1, port3, timed)."""
    mod = sys.modules.get(f"{__name__}.{MODULE_OF[name]}")
    fn = getattr(mod, "second_look", None)
    if callable(fn):
        try:
            txt = fn(name)
        except KeyError:
            txt = None
        if txt:
            return str(txt)
    notes = REGISTRY[name][3]
    i = notes.lower().find("second look")
    if i < 0:
        return None
    start = max(notes.rfind(". ", 0, i), notes.rfind("; ", 0, i))
    return notes[start + 2 if start >= 0 else 0:].strip()


def penalty_for(name: str, sess: str | None = None):
    """The failure-penalty text that applies to a member of `name` in session `sess` (admission then also needs the PICK
    plateau), or None. donchian carries it in pm only, first_bar_mom in every session (ORCHESTRATOR DECISIONS 4); with
    sess None the family's penalty is returned whatever its sessions."""
    lib = library(name)
    ps = lib.get("penalty_sess")
    return lib["penalty"] if lib["penalty"] and (ps is None or sess is None or sess in ps) else None


def columns(name: str) -> tuple:
    """The feature columns of a registered family (its class's FEATURES), for l2sim.L2Features / score.C2Features."""
    return tuple(REGISTRY[name][0].FEATURES)


def features_for(name: str, extra: tuple = (), c2_seed: int | None = None):
    """The `features=` loader of a family's run: None when it reads no feature (and `extra` is empty), else
    l2sim.L2Features(FEATURES + extra) -- or the C2 feature-shuffle null score.C2Features(..., seed=c2_seed).
    extra: the columns of the Template's own L2 options (l2sim.template_feature_needs(params))."""
    cols = tuple(dict.fromkeys(tuple(REGISTRY[name][0].FEATURES) + tuple(extra)))
    if not cols:
        return None
    if c2_seed is None:
        return l2sim.L2Features(cols)
    import score
    return score.C2Features(cols, seed=int(c2_seed))


def library(name: str) -> dict:
    """The edge-library meta of a family; KeyError (with the reason) when it is registered without one."""
    if name not in LIBRARY:
        why = ERRORS.get(name) or ("registered as a 4-tuple: add the 5th field {'rationale': ..., 'complexity': ...}"
                                   if name in REGISTRY else "not registered")
        raise KeyError(f"{name!r} is not an edge-library family: {why}")
    return LIBRARY[name]


def unit_inputs(name: str, tf: str, sess: str = "all") -> dict:
    """The base inputs of a unit (family x tf): the registered defaults + tf + sess. run_menus runs every cell as three
    independent instances -- sess 'all' (the tester's five), 'pre' and 'eve' -- and merges their trades (a time-fired
    family ignores sess and is one instance)."""
    return {**REGISTRY[name][1], "tf": str(tf), "sess": sess}


def unit_grid(name: str, root: str, tf: str, sess: str = "all") -> list:
    """THE MENU GRID of one unit (family x root x tf): every registered family-parameter variant x the 32 exit cells
    (l2sim.menu_grid). The plateau is judged over ALL of these cells, per session.
    STAGE 2b hooks (classmethods of the family class, both optional): `unit_exits(root)` -> the family's OWN exit cells in
    place of the 32 menu cells; `author_cells(root, tf)` -> [(extra inputs, exit cell)] = one INFORMATION-ONLY cell per
    variant each, appended after the menu cells with 'info': True (run and stored, left out of library.plateau)."""
    lib = library(name)
    if root not in lib["roots"]:
        raise ValueError(f"{name} is not registered for root {root} (roots {lib['roots']})")
    cls = REGISTRY[name][0]
    if str(tf) not in cls.SCREEN_TFS:
        raise ValueError(f"{name}: tf {tf} is not one of its SCREEN_TFS {cls.SCREEN_TFS}")
    base = unit_inputs(name, tf, sess)
    exits = cls.unit_exits(root) if hasattr(cls, "unit_exits") else None       # a family with its OWN exit cells (round1 N7)
    grid = l2sim.menu_grid(cls, base, root, lib["variants"], exits)
    author = getattr(cls, "author_cells", None)
    if author is not None:                           # EDGE_SPEC stage 2b "author cells": information only, flagged `info`
        nx = len(grid) // len(lib["variants"])
        for vi, v in enumerate(lib["variants"]):
            for j, (extra, x) in enumerate(author(root, str(tf))):
                vv = {**v, **extra}
                grid.append({"id": f"{l2sim.cell_id(vv)}_{l2sim.cell_id(x)}", "variant": vv, "exit": dict(x), "vi": vi,
                             "xi": nx + j, "spec": (cls, {**base, **vv, **x}), "info": True})
    return grid


def screen_inputs(name: str, tf: str) -> dict:
    """The inputs of the family's screen run at one tf: its registered defaults + tf, all sessions."""
    return {**REGISTRY[name][1], "tf": str(tf), "sess": "all"}


load()


def main() -> int:
    for name, (cls, inputs, both, notes) in sorted(REGISTRY.items()):
        print(f"{name:16s} {MODULE_OF[name]}.{cls.__name__:18s} tfs {','.join(cls.SCREEN_TFS):6s} both_sides {both!s:5s} "
              f"inputs {inputs}  features {','.join(cls.FEATURES)}  | {notes}")
        if name in LIBRARY:
            lb = LIBRARY[name]
            print(f"{'':16s} LIBRARY roots {','.join(lb['roots'])}  variants {len(lb['variants'])}  complexity {lb['complexity']}"
                  f"{'  WEAK' if lb['weak'] else ''}{'  MIRROR ' + lb['mirror'] if lb.get('mirror') else ''}"
                  f"{'  PENALTY' + (' ' + '/'.join(lb['penalty_sess']) if lb.get('penalty_sess') else '') if lb['penalty'] else ''}"
                  f"{'  SECOND-LOOK' if lb.get('second_look') else ''}  rationale: {lb['rationale']}")
    for k, v in ERRORS.items():
        print(f"ERROR {k}: {v}")
    print(f"{len(REGISTRY)} families ({len(LIBRARY)} edge-library), {len(ERRORS)} errors")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
