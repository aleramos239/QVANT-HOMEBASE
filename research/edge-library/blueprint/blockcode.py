"""blockcode.py -- `bp.py blockcode`: THE TOOLKIT AS A BROWSABLE LIST, EACH BLOCK WITH THE CODE THAT IMPLEMENTS IT (the Lab's Toolkit view).

The list is blocklist.blocks() (families, filters with their sides, limits, exits, sessions, bars, markets, the days); this module adds,
for every entry, WHERE ITS CODE IS -- read from the code itself, never typed per block, so a new block shows up with its code:
    filter    its FILTERS / PLAIN / SCHEMA entries (found by evaluating the registry's own dict literals, loops and comprehensions,
              so `pdz_{k}` for k in RG.KINDS finds the right line), the statement of `Blocks.allowed` that reads its setting (found
              by the setting's name, also through `for blk in LINE_BLOCKS:` style loops), the constants that statement uses, and
              every function of the toolkit's engine it calls (ranges.py, zones.py, levels.py, indicators.py ..., two levels deep)
    family    its class, its entry in the module's FAMILIES, its range height (HEIGHTS)
    the rest  the template file (templates/*.json) and the function or table that reads it
A source is {file, start, end, code}: the file relative to the repository, the 1-based line range, the lines as they are on disk.
The result of the command is {groups: [{id, title, words, items: [{id, name, sub, words, sides?, markets, runs, why_not, parts: [{label, src}]}]}],
sources: {id: source}, counts, text}. Reads code and templates only: no store, no tape, no run.
"""
from __future__ import annotations

import ast
import inspect
import itertools
import sys
from pathlib import Path

import judge as J
import run_idea as RI
import run_menus as RM

from . import api
from . import blocklist as BL
from . import rules as R
from . import runner as RUN

EDGE = Path(__file__).resolve().parents[1]          # research/edge-library
REPO = EDGE.parents[1]
MAX_FUNCS = 14                                      # functions listed after a filter's own code
MAX_DEPTH = 2                                       # a called function's own calls
TEMPLATES = EDGE / "blueprint" / "templates"

_text: dict = {}                                    # path -> source text lines
_tree: dict = {}                                    # path -> parsed module


def _lines(path) -> list:
    path = str(path)
    if path not in _text:
        _text[path] = Path(path).read_text(encoding="utf-8").splitlines()
    return _text[path]


def _parse(path):
    path = str(path)
    if path not in _tree:
        _tree[path] = ast.parse("\n".join(_lines(path)))
    return _tree[path]


def _rel(path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def _ours(obj) -> bool:
    """A function or class of the toolkit's own engine (not a library, not a test)."""
    try:
        f = Path(inspect.getsourcefile(obj) or "").resolve()
    except TypeError:
        return False
    return f.is_file() and EDGE in f.parents and "tests" not in f.parts


class Sources:
    """The sources one result holds, each once, by id."""

    def __init__(self):
        self.by_id: dict = {}

    def add(self, path, start: int, end: int) -> str:
        sid = f"{_rel(path)}:{start}-{end}"
        if sid not in self.by_id:
            self.by_id[sid] = {"file": _rel(path), "start": start, "end": end, "code": "\n".join(_lines(path)[start - 1:end])}
        return sid


# ---------------------------------------------------------------- the registry's own tables, found by evaluating them

def _ev(node, globs, env):
    return eval(compile(ast.Expression(node), "<blockcode>", "eval"), globs, env)  # noqa: S307 -- the engine's own source text


def _bind(env: dict, target, value) -> dict:
    out = dict(env)

    def put(t, v):
        if isinstance(t, ast.Name):
            out[t.id] = v
        else:
            for x, y in zip(t.elts, v):
                put(x, y)
    put(target, value)
    return out


def table_lines(tree_body: list, container: str, globs: dict, match) -> list:
    """[(start, end)] of what puts an entry whose key `match` accepts into the table `container` (a dict literal, `.update({...})`,
    `NAME[key] = ...`, `**{... for k in ...}`), also inside `for` loops: the entry's own lines, or the whole loop when the entry
    is made by one. `tree_body` is a module's or a class's statements."""
    hits: list = []

    def entry_keys(d: ast.Dict, envs: list, top):
        for k, v in zip(d.keys, d.values):
            if k is None:
                if isinstance(v, ast.DictComp) and len(v.generators) == 1:
                    g = v.generators[0]
                    for env in envs:
                        try:
                            vals = list(_ev(g.iter, globs, env))
                        except Exception:       # noqa: BLE001
                            continue
                        for x in vals:
                            try:
                                if match(_ev(v.key, globs, _bind(env, g.target, x))):
                                    hits.append((top.lineno, top.end_lineno) if top is not None else (v.lineno, v.end_lineno))
                                    break
                            except Exception:   # noqa: BLE001
                                continue
                elif isinstance(v, ast.Dict):
                    entry_keys(v, envs, top)
                continue
            for env in envs:
                try:
                    if match(_ev(k, globs, env)):
                        hits.append((top.lineno, top.end_lineno) if top is not None else (k.lineno, v.end_lineno))
                        break
                except Exception:               # noqa: BLE001
                    continue

    def walk(stmts: list, envs: list, top):
        for st in stmts:
            if isinstance(st, ast.For):
                new = []
                for env in envs:
                    try:
                        new += [_bind(env, st.target, x) for x in list(_ev(st.iter, globs, env))]
                    except Exception:           # noqa: BLE001
                        continue
                walk(st.body, new, top or st)
            elif isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and st.targets[0].id == container \
                    and isinstance(st.value, ast.Dict):
                entry_keys(st.value, envs, top)
            elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute) \
                    and st.value.func.attr == "update" and isinstance(st.value.func.value, ast.Name) and st.value.func.value.id == container \
                    and st.value.args and isinstance(st.value.args[0], ast.Dict):
                entry_keys(st.value.args[0], envs, top)
            elif isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Subscript) \
                    and isinstance(st.targets[0].value, ast.Name) and st.targets[0].value.id == container:
                for env in envs:
                    try:
                        if match(_ev(st.targets[0].slice, globs, env)):
                            hits.append((top.lineno, top.end_lineno) if top is not None else (st.lineno, st.end_lineno))
                            break
                    except Exception:           # noqa: BLE001
                        continue
    walk(tree_body, [{}], None)
    return sorted(set(hits))


# ---------------------------------------------------------------- code that reads a setting, and what it calls

def _mentions(node, key: str, globs: dict, env: dict) -> bool:
    """Does this code name the setting `key`: the string itself, or an f-string such as f"f_{blk}" / f"f_pdz_{k}" whose loop variable
    (bound in `env`) gives it."""
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and n.value == key:
            return True
        if isinstance(n, ast.JoinedStr):
            try:
                if _ev(n, globs, env) == key:
                    return True
            except Exception:                   # noqa: BLE001
                continue
    return False


def statements_for(func: ast.FunctionDef, key: str, globs: dict) -> list:
    """The statements of `func` that read the setting `key`: the `if` that tests it, or, where a loop over blocks reads it, the
    loop (or the loop's own `if` when the loop holds several blocks). [(start, end, node)]."""
    out: list = []

    def walk(stmts, envs, loop):
        for st in stmts:
            if isinstance(st, ast.For):
                new = []
                for env in envs:
                    try:
                        new += [_bind(env, st.target, x) for x in list(_ev(st.iter, globs, env))]
                    except Exception:           # noqa: BLE001
                        continue
                walk(st.body, new, st)
            elif isinstance(st, ast.If) and any(_mentions(st.test, key, globs, env) for env in envs):
                out.append((st.lineno, st.end_lineno, st))
            elif loop is not None and any(_mentions(st, key, globs, env) for env in envs) and not isinstance(st, ast.If):
                out.append((loop.lineno, loop.end_lineno, loop))        # `mode = p[f"f_{blk}"]`: the loop is the check
    walk(func.body, [{}], None)
    uniq = {}
    for a, b, n in out:
        uniq.setdefault((a, b), n)
    return [(a, b, n) for (a, b), n in sorted(uniq.items())]


def called(nodes: list, globs: dict, cls) -> list:
    """The toolkit's own functions and methods named by calls in `nodes`, in order of first mention: [object]."""
    seen, out = set(), []
    for root in nodes:
        for n in ast.walk(root):
            if not isinstance(n, ast.Call):
                continue
            f, obj = n.func, None
            if isinstance(f, ast.Name):
                obj = globs.get(f.id)
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                base = f.value.id
                if base == "self" and cls is not None:
                    obj = getattr(cls, f.attr, None)
                elif inspect.ismodule(globs.get(base)):
                    obj = getattr(globs[base], f.attr, None)
            if inspect.isfunction(obj) and _ours(obj) and obj not in seen:
                seen.add(obj)
                out.append(obj)
    return out


def constants(nodes: list, mod, tree) -> list:
    """[(start, end)] of the module-level `NAME = value` lines of `mod` that `nodes` use (the numbers a block compares with)."""
    names = {n.id for root in nodes for n in ast.walk(root) if isinstance(n, ast.Name) and n.id.isupper() and len(n.id) > 2}
    out = []
    for st in tree.body:
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and st.targets[0].id in names:
            out.append((st.lineno, st.end_lineno))
    return out


def fn_range(obj) -> tuple:
    src, start = inspect.getsourcelines(obj)
    return Path(inspect.getsourcefile(obj)), start, start + len(src) - 1


def called_parts(src: Sources, nodes: list, globs: dict, cls, parts: list):
    """Adds `parts` for the functions `nodes` call, then theirs (MAX_DEPTH levels, MAX_FUNCS in all)."""
    done: set = set()
    queue = [(f, 1) for f in called(nodes, globs, cls)]
    while queue and len(done) < MAX_FUNCS:
        f, depth = queue.pop(0)
        if f in done:
            continue
        done.add(f)
        path, a, b = fn_range(f)
        if b - a > 220:                                  # a whole engine class is not "the function it calls"
            continue
        label = f"{Path(path).stem}.{f.__qualname__}" if depth == 1 else f"{Path(path).stem}.{f.__qualname__} (called by the above)"
        parts.append({"label": label, "src": src.add(path, a, b)})
        if depth < MAX_DEPTH:
            node = next((n for n in ast.walk(_parse(path)) if isinstance(n, ast.FunctionDef) and n.lineno == a), None)
            if node is not None:
                queue += [(g, depth + 1) for g in called([node], inspect.getmodule(f).__dict__, None)]


# ---------------------------------------------------------------- the entries

def _blocks_module():
    return RUN._blocks()


def filter_item(src: Sources, eng, f: dict, sides: list) -> dict:
    """One filter block: its list line and the parts of its code."""
    block = f["block"]
    path = Path(inspect.getsourcefile(eng))
    tree, globs = _parse(path), eng.__dict__
    cls_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Blocks")
    allowed = next(n for n in cls_node.body if isinstance(n, ast.FunctionDef) and n.name == "allowed")
    keys = sorted({k for s in eng.FILTERS[block].values() for k in s})
    parts: list = []
    for a, b in table_lines(tree.body, "FILTERS", globs, lambda k: k == block)[:1]:
        parts.append({"label": "Registered: its sides and the settings they switch on (FILTERS)", "src": src.add(path, a, b)})
    plain = sorted({h for s in sides for h in table_lines(tree.body, "PLAIN", globs, lambda k, s=s: k == (block, s))})
    for a, b in _merge(plain):
        parts.append({"label": "Its words (PLAIN)", "src": src.add(path, a, b)})
    for key in keys[:1]:
        for a, b in table_lines(cls_node.body, "SCHEMA", globs, lambda k, key=key: k == key)[:1]:
            parts.append({"label": f"Its setting {key} (Blocks.SCHEMA)", "src": src.add(path, a, b)})
    nodes: list = []
    for key in keys:
        found = statements_for(allowed, key, globs)
        for a, b, n in found:
            parts.append({"label": f"The check: where an entry is allowed or refused (Blocks.allowed, {key})", "src": src.add(path, a, b)})
            nodes.append(n)
        if not found:                                    # read somewhere else (the Level 2 `book` filter, the VWAP, live in the simulator's Template): the function that names it
            for mod in (sys.modules.get("l2sim"),):
                mp = Path(inspect.getsourcefile(mod))
                for fn in [n for n in ast.walk(_parse(mp)) if isinstance(n, ast.FunctionDef)]:
                    if not any(isinstance(n, ast.Constant) and n.value == key for n in ast.walk(fn)):
                        continue
                    stm = statements_for(fn, key, mod.__dict__)
                    for a, b, n in stm or [(fn.lineno, fn.end_lineno, fn)]:
                        if b - a < 120:
                            parts.append({"label": f"The check, in the simulator ({fn.name}, {key})", "src": src.add(mp, a, b)})
                            nodes.append(n)
    for a, b in constants(nodes, eng, tree):
        parts.append({"label": "A number it uses", "src": src.add(path, a, b)})
    called_parts(src, nodes, globs, eng.Blocks, parts)
    return {"id": f"filter:{block}", "name": block, "sub": " | ".join(sides), "words": sides_words(f, eng, block), "sides": [
        {"side": s, "words": eng.PLAIN[(block, s)]} for s in sides], "markets": f["markets"], "runs": f["runs"], "why_not": f["why_not"], "parts": _dedupe(parts)}


def _merge(spans: list) -> list:
    """Line spans that touch become one."""
    out: list = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def sides_words(f, eng, block) -> str:
    first = next(iter(eng.FILTERS[block]))
    return eng.PLAIN[(block, first)]


def _dedupe(parts: list) -> list:
    seen, out = set(), []
    for p in parts:
        if p["src"] not in seen:
            seen.add(p["src"])
            out.append(p)
    return out


def family_item(src: Sources, eng, f: dict) -> dict:
    name = f["name"]
    cls = eng.BASES[name][0]
    parts: list = []
    cpath, a, b = fn_range(cls)
    parts.append({"label": f"The family: class {cls.__name__}", "src": src.add(cpath, a, b)})
    mod = inspect.getmodule(cls)
    for m in (mod, eng):
        mp = Path(inspect.getsourcefile(m))
        hit = table_lines(_parse(mp).body, "FAMILIES", m.__dict__, lambda k: k == name)
        if hit:
            parts.append({"label": "Registered: its name, class and library entry (FAMILIES)", "src": src.add(mp, *hit[0])})
            break
    epath = Path(inspect.getsourcefile(eng))
    for a, b in table_lines(_parse(epath).body, "HEIGHTS", eng.__dict__, lambda k: k == name)[:1]:
        parts.append({"label": "Its range height, for a stop that is a share of it (HEIGHTS)", "src": src.add(epath, a, b)})
    parts.append({"label": "How the blocks wrap it (blocks._wrap)", "src": src.add(epath, *fn_range(eng._wrap)[1:])})
    return {"id": f"family:{name}", "name": name, "sub": f"bars {', '.join(f['bars'])}", "words": f["does"], "markets": f["markets"],
            "runs": f["runs"], "why_not": f["why_not"], "parts": _dedupe(parts)}


def other_family_item(src: Sources, eng, fam, name: str) -> dict:
    """A family of the registry that is no blueprint block (time-fired, Level 2, straddles): listed with its code, marked not yet."""
    cls, _inputs, _both, notes = fam.REGISTRY[name][:4]
    head, sep, rest = str(notes).partition(": ")
    words = rest if sep and len(head) <= 30 else str(notes)
    l2 = bool(tuple(getattr(cls, "FEATURES", ())))
    parts = [{"label": f"The family: class {cls.__name__}", "src": src.add(*fn_range(cls))}]
    mod = inspect.getmodule(cls)
    mp = Path(inspect.getsourcefile(mod))
    hit = table_lines(_parse(mp).body, "FAMILIES", mod.__dict__, lambda k: k == name)
    if hit:
        parts.append({"label": "Registered: its name, class and notes (FAMILIES)", "src": src.add(mp, *hit[0])})
    return {"id": f"other:{name}", "name": name, "sub": "Level 2" if l2 else "fires at a clock time or on an event", "words": words, "markets": ["NQ"] if l2 else [],
            "runs": False, "why_not": "not a bar-based block: a clock-time or Level 2 idea comes later", "parts": _dedupe(parts)}


def helper_items(src: Sources) -> list:
    """The engine's indicator and zone functions the filters call: every public function of their modules, with its first docstring line."""
    import importlib
    out = []
    for mod_name in ("indicators", "zones", "ranges", "levels", "flowtab"):
        m = importlib.import_module(f"engine.{mod_name}")
        for n, f in vars(m).items():
            if inspect.isfunction(f) and f.__module__ == m.__name__ and not n.startswith("_"):
                doc = (inspect.getdoc(f) or "").strip().splitlines()
                out.append({"id": f"helper:{mod_name}.{n}", "name": f"{mod_name}.{n}", "sub": "", "words": doc[0] if doc else f"{n}({', '.join(inspect.signature(f).parameters)})",
                            "markets": [], "runs": True, "why_not": None, "parts": [{"label": f"{mod_name}.{n}", "src": src.add(*fn_range(f))}]})
    return out


def _json(src: Sources, name: str, label: str) -> dict:
    p = TEMPLATES / name
    return {"label": label, "src": src.add(p, 1, len(_lines(p)))}


def _func(src: Sources, obj, label: str) -> dict:
    return {"label": label, "src": src.add(*fn_range(obj))}


def _assign(src: Sources, mod, name: str, label: str) -> dict:
    mp = Path(inspect.getsourcefile(mod))
    for st in _parse(mp).body:
        if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in st.targets):
            return {"label": label, "src": src.add(mp, st.lineno, st.end_lineno)}
    raise LookupError(f"{name} is not a module-level assignment of {mp.name}")


def plain_items(src: Sources, eng, B: dict) -> list:
    """The toolkit's other parts (limits, exits, sessions, bar sizes, markets, days, random tables, Monte Carlo, size steps): each with its
    template and the code that reads it."""
    import l2sim as S
    from . import mc as MC
    it = lambda i, n, words, parts, sub="": {"id": i, "name": n, "sub": sub, "words": words, "markets": [], "runs": True, "why_not": None, "parts": _dedupe(parts)}  # noqa: E731
    out = {"limits": [], "exits": [], "sessions": [], "bars": [], "markets": [], "days": [], "tables": []}
    for x in B["limits"]:
        out["limits"].append(it(f"limit:{x['name']}", x["name"], x["words"], [_assign(src, BL, "LIMITS", "Its words (LIMITS)"), _assign(src, RI, "LIMIT_KEYS", "The limits an idea may set (LIMIT_KEYS)")]))
    ex = B["exits"]
    base = [_json(src, "exit_menu.json", "The table (exit_menu.json)"), _func(src, R.exit_menu, "The cells for a market (rules.exit_menu)"), _func(src, S.cell_id, "A cell's name (l2sim.cell_id)")]
    out["exits"] += [
        it("exit:stops", "stops", f"{len(ex['stops']['atr'])} ATR stops, fixed points a market, percent of the entry price", base, "the stop of every trade"),
        it("exit:targets", "targets", "a multiple of the stop distance, or none: the trade runs to its stop or the flat time", base, "the target of every trade"),
        it("exit:flat", "flat time", f"every trade is flat by {ex['flat_et']} ET ({ex['flat_et_half_day']} on half days)", base, "when a trade must end")]
    out["exits"].append(it("exit:blueprint_menu", "the exit menu a family reads", "the table's cells as the engine builds them, with the targets added in version 1.1",
                           [_func(src, eng.menu_blueprint, "The menu (blocks.menu_blueprint)"), _func(src, eng.exits, "Which menu an idea gets (blocks.exits)")]))
    for s in B["sessions"]:
        out["sessions"].append(it(f"session:{s['name']}", s["name"], s["words"], [_assign(src, J, "SESS_PLAIN", "The words (SESS_PLAIN)"), _assign(src, RM, "DAY_PASSES", "The sessions an idea may use (DAY_PASSES)")]))
    out["bars"].append(it("bars:sizes", "bar sizes", f"{', '.join(B['bars'])} minutes (a family may run on fewer)", [_assign(src, RM.registry(), "TFS", "The bar sizes (TFS)")]))
    for m in B["markets"]:
        out["markets"].append(it(f"market:{m['market']}", m["market"], f"the average trade must reach ${m['floor']:g} after costs at 1 contract; ${m['point_value']:g} a point, tick {m['tick']:g}",
                                 [_json(src, "costs.json", "Costs and contract (costs.json)"), _func(src, R.need, "The floor, read from the law's line (rules.need)")]))
    rg = B["ranges"]
    out["days"] += [it("days:build", "build days", f"{rg['build']['start']} to {rg['build']['end']}: all tuning happens here", [_json(src, "ranges.json", "The days (ranges.json)")]),
                    it("days:test", "test days", f"{rg['test']['start']} on: read once, only for a locked strategy", [_json(src, "ranges.json", "The days (ranges.json)")])]
    out["tables"] += [it("table:random", "random tables", f"{B['random_tables']['draws']:,} draws from {B['random_tables']['seeds']} seeds of random entries with the same exits", [_json(src, "control.json", "The tables (control.json)")]),
                      it("table:mc", "Monte Carlo", f"{B['montecarlo']['build']['need'] * 100:g} % of reshuffled runs on build, {B['montecarlo']['test']['need'] * 100:g} % on test", [_json(src, "montecarlo.json", "The settings (montecarlo.json)"), _func(src, MC.reshuffle, "The reshuffle (mc.reshuffle)")]),
                      it("table:sizes", "size steps", f"steps in micros: {', '.join(f'{x:g}' for x in B['sizes']['steps'])}", [_json(src, "sizes.json", "The steps (sizes.json)")])]
    return out


GROUPS = (("families", "Entry triggers", "What starts a trade. One per idea."), ("other", "Other families", "In the library, not blueprint blocks yet: clock-time and Level 2 ideas."), ("filters", "Filters", "Switch an entry on or off. Two sides each; at most two per idea."),
          ("limits", "Limits", "How many entries, one side or both."), ("exits", "Exits", "One table for every idea."), ("sessions", "Sessions", "When an idea trades (New York time)."),
          ("bars", "Bar sizes", "The minutes in a bar."), ("markets", "Markets", "What an idea trades, with its cost floor."), ("days", "Days", "Build days and test days."),
          ("tables", "Tests", "The random tables, the Monte Carlo and the size steps."), ("helpers", "Indicators and helpers", "The engine functions the filters call."))


def toolkit() -> dict:
    """`bp.py blockcode`: the list with its code (module docstring)."""
    eng = _blocks_module()
    B = BL.blocks()["blocks"]
    src = Sources()
    by_block: dict = {}
    for f in B["filters"]:
        by_block.setdefault(f["block"], []).append(f)
    items = {"families": [family_item(src, eng, f) for f in B["families"]],
             "filters": [filter_item(src, eng, fs[0], [x["side"] for x in fs]) for fs in by_block.values()]}
    fam = RM.registry()
    items["other"] = [other_family_item(src, eng, fam, n) for n in B["other_families"]]
    items["helpers"] = helper_items(src)
    items.update(plain_items(src, eng, B))
    groups = [{"id": g, "title": title, "words": words, "items": items[g]} for g, title, words in GROUPS]
    n = sum(len(g["items"]) for g in groups)
    lines = [f"THE TOOLKIT: {n} blocks, each with its code (the Lab, Toolkit view)"] + [f"  {g['title']}: {len(g['items'])}" for g in groups]
    return api.result("blockcode", None, groups=groups, sources=src.by_id, counts={g["id"]: len(g["items"]) for g in groups}, text="\n".join(lines), next="")
