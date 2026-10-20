"""What a change of main needs on the server (deploy/linux/vpssync.sh), read from the code itself -- nothing is run.

    python3 vpssync_plan.py <tree> <changed path>...
        -> one line per service to restart:  service homebase-charts | homebase | homebase-labrun
           one line per unit to (re)install:  unit homebase-charts.service
           a line `block <why>` when the change must not ship by itself (a new dependency)

<tree> is a clean copy of the commit. Its homebase/ package is read as a static import graph (ast): a changed module
restarts every service whose entry module reaches it -- imports inside functions count, so the answer errs towards a
restart. A changed data file restarts every service that reaches a module of its folder. homebase/static/ is served
from disk on every request: nothing restarts for it. A changed unit file (deploy/linux/<unit>) is installed again and
its service restarted. Anything else (tests, tools, docs, research code) restarts nothing.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ENTRIES = {"homebase-charts": "homebase.charts.__main__",       # python -m homebase.charts
           "homebase": "homebase.server",                       # uvicorn homebase.server:app
           "homebase-labrun": "homebase.labrun.__main__"}       # python -m homebase.labrun
UNITS = {"homebase.service": "homebase", "homebase-charts.service": "homebase-charts",
         "homebase-labrun.service": "homebase-labrun", "homebase-ticks.service": None, "homebase-ticks.timer": None}
NO_RESTART = ("homebase/static/",)


def module_of(rel: str) -> str | None:
    p = Path(rel)
    if p.suffix != ".py" or p.parts[0] != "homebase":
        return None
    parts = list(p.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def graph(tree: Path) -> dict[str, set[str]]:
    """module -> the homebase modules it imports (and the packages above each one, which Python runs first)."""
    mods = {m: f for f in (tree / "homebase").rglob("*.py") if (m := module_of(str(f.relative_to(tree))))}
    out: dict[str, set[str]] = {}
    for mod, f in mods.items():
        pkg = mod if f.name == "__init__.py" else mod.rpartition(".")[0]
        got: set[str] = set()
        try:
            nodes = ast.walk(ast.parse(f.read_text(encoding="utf-8")))
        except (SyntaxError, UnicodeDecodeError):
            nodes = ()
        for n in nodes:
            names: list[str] = []
            if isinstance(n, ast.Import):
                names = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                base = n.module or ""
                if n.level:
                    up = pkg.split(".")
                    up = up[:len(up) - (n.level - 1)] if n.level > 1 else up
                    base = ".".join([*up, *([n.module] if n.module else [])])
                names = [base] + [f"{base}.{a.name}" for a in n.names]
            for name in names:
                if name in mods:
                    got.add(name)
                    parts = name.split(".")
                    got.update(".".join(parts[:i]) for i in range(1, len(parts)) if ".".join(parts[:i]) in mods)
        out[mod] = got
    return out


def reach(g: dict[str, set[str]], start: str) -> set[str]:
    seen, todo = set(), [start]
    parts = start.split(".")
    todo += [".".join(parts[:i]) for i in range(1, len(parts))]        # its packages run first
    while todo:
        m = todo.pop()
        if m in seen or m not in g:
            continue
        seen.add(m)
        todo += g[m]
    return seen


def plan(tree: Path, changed: list[str]) -> list[str]:
    g = graph(tree)
    reached = {svc: reach(g, entry) for svc, entry in ENTRIES.items()}
    services, units, lines = set(), set(), []
    for rel in changed:
        if rel == "requirements.txt":
            lines.append("block requirements.txt changed: install the new packages on the server by hand first")
            continue
        if rel.startswith("deploy/linux/") and Path(rel).name in UNITS:
            units.add(Path(rel).name)
            if UNITS[Path(rel).name]:
                services.add(UNITS[Path(rel).name])
            continue
        if not rel.startswith("homebase/") or rel.startswith(NO_RESTART):
            continue
        mod = module_of(rel)
        parts = list(Path(rel).parent.parts)                            # a data file: the nearest folder with code
        while len(parts) > 1 and not any(m == ".".join(parts) or m.startswith(".".join(parts) + ".") for m in g):
            parts.pop()
        folder = ".".join(parts)
        for svc, mods in reached.items():
            if (mod is not None and mod in mods) or (mod is None and any(m == folder or m.startswith(folder + ".") for m in mods)):
                services.add(svc)
    lines += [f"unit {u}" for u in sorted(units)]
    lines += [f"service {s}" for s in ENTRIES if s in services]          # in restart order: charts, desk, runner
    return lines


if __name__ == "__main__":
    print("\n".join(plan(Path(sys.argv[1]), sys.argv[2:])))
