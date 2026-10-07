"""arsenal -- EVERY TOOL WE HAVE, in one catalog the app keeps and the Lab shows (its Arsenal tab).

    blocks and library   what an idea is built from: entry triggers, filters, exits, sessions ..., the other families of the library,
                         the engine's indicator helpers -- each with its code (the research toolkit, `bp.py blockcode`)
    chat tools           every tool a chat has through the connector (claude_mcp.tools.SPECS): the strategy tester's, the blueprint's,
                         the desk's views -- each with its definition and the method that runs it
    skills               the Claude skills on this machine (~/.claude/skills, the repository's .claude/skills): the skill file and its scripts
    scripts              the repository's own scripts (tools/, the research toolkit's command line files)

The catalog is DERIVED from the code and the skill folders (ast / inspect / the folders themselves), never listed by hand: a new tool,
block or skill is in it after the next build. It is SAVED as one JSON file (~/.homebase/arsenal.json, HOMEBASE_ARSENAL names another):
`get()` returns the saved catalog while no file it was built from has changed, and builds + saves a new one when one has.
Shape (the same the Lab's list reads): {groups: [{id, title, words, items: [{id, name, sub, words, markets, runs, why_not, parts: [{label, src}]}]}],
sources: {id: {file, start, end, code, plain?, note?}}, counts, built, stamp, notes}. Reads files only: nothing here runs a tool.

    .venv/bin/python -m homebase.arsenal        build now, save it and print the counts
"""
from __future__ import annotations

import ast
import datetime as dt
import inspect
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Callable

from . import paths

ENV = "HOMEBASE_ARSENAL"
MAX_LINES = 500                                     # a longer file is cut here, and says so
MAX_CALLED = 4                                      # methods / functions a chat tool's method calls, listed after it
SCRIPT_DIRS = ("tools", "research/edge-library")    # where the repository's own scripts live (top-level .py files only)
PLAIN_SUFFIX = {".md": 1, ".json": 1, ".txt": 1, ".sh": 1, ".yaml": 1, ".yml": 1, ".toml": 1}   # shown as text: the Python colours would mislead


def arsenal_path() -> Path:
    v = os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "arsenal.json"


def skill_dirs() -> list:
    return [Path.home() / ".claude" / "skills", paths.repo_root() / ".claude" / "skills"]


def _rel(p: Path) -> str:
    p = Path(p).resolve()
    for base, tag in ((paths.repo_root().resolve(), ""), (Path.home().resolve(), "~/")):
        try:
            return tag + str(p.relative_to(base))
        except ValueError:
            continue
    return str(p)


class Sources:
    """The sources one catalog holds, each once, by id (file:start-end)."""

    def __init__(self):
        self.by_id: dict = {}

    def add(self, path, start: int, end: int, plain: bool = False, note: str = "") -> str:
        path = Path(path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        end = min(end, len(lines))
        cut = end - start + 1 > MAX_LINES
        if cut:
            note = note or f"The first {MAX_LINES} of {end - start + 1} lines."
            end = start + MAX_LINES - 1
        sid = f"{_rel(path)}:{start}-{end}"
        if sid not in self.by_id:
            s = {"file": _rel(path), "start": start, "end": end, "code": "\n".join(lines[start - 1:end])}
            if plain:
                s["plain"] = True
            if note:
                s["note"] = note
            self.by_id[sid] = s
        return sid

    def whole(self, path) -> str:
        path = Path(path)
        n = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        return self.add(path, 1, max(1, n), plain=path.suffix.lower() in PLAIN_SUFFIX)


def _item(i: str, name: str, words: str, parts: list, sub: str = "") -> dict:
    return {"id": i, "name": name, "sub": sub, "words": words, "markets": [], "runs": None, "why_not": None, "parts": parts}


def _first_sentence(text: str, n: int = 220) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    m = re.match(r"(.+?[.!?])(\s|$)", t)
    t = m.group(1) if m else t
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


# ---------------------------------------------------------------- chat tools

def _spec_lines(path: Path, name: str):
    """(start, end) of the `_spec("name", ...)` call that defines the tool `name` in a module, or None."""
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_spec" and n.args \
                and isinstance(n.args[0], ast.Constant) and n.args[0].value == name:
            return n.lineno, n.end_lineno
    return None


def _called(fn, owner, globs: dict) -> list:
    """The methods of `owner` (self.x) and the module's own functions that `fn` calls, in order of first mention."""
    try:
        node = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, SyntaxError):
        return []
    seen, out = set(), []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f, obj = n.func, None
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "self":
            obj = getattr(owner, f.attr, None)
        elif isinstance(f, ast.Name):
            obj = globs.get(f.id)
        if inspect.isfunction(obj) and obj is not fn and obj not in seen and _ours(obj) and not getattr(obj, "__name__", "").startswith("t_"):
            seen.add(obj)
            out.append(obj)
    return out[:MAX_CALLED]


def _ours(obj) -> bool:
    try:
        f = Path(inspect.getsourcefile(obj) or "").resolve()
    except TypeError:
        return False
    return f.is_file() and paths.repo_root().resolve() in f.parents and "tests" not in f.parts


def _fn_lines(obj) -> tuple:
    src, start = inspect.getsourcelines(obj)
    return Path(inspect.getsourcefile(obj)), start, start + len(src) - 1


def chat_tools(src: Sources) -> tuple:
    """Groups of the connector's tools: each with its definition (the `_spec` call) and the method that runs it (`Toolbox.t_<name>`)."""
    from .claude_mcp import blueprint_tools as BT
    from .claude_mcp import desk_tools as DT
    from .claude_mcp import tools as T
    bp, desk = {s["name"] for s in BT.SPECS}, {s["name"] for s in DT.SPECS}
    mods = [Path(inspect.getsourcefile(m)) for m in (T, BT, DT)]
    out = {"tester": [], "blueprint": [], "desk": []}
    for s in T.SPECS:
        name = s["name"]
        kind = "blueprint" if name in bp else "desk" if name in desk else "tester"
        parts = []
        for mp in mods:
            hit = _spec_lines(mp, name)
            if hit:
                parts.append({"label": "What a chat sees: its name, words and inputs", "src": src.add(mp, *hit)})
                break
        fn = getattr(T.Toolbox, f"t_{name}", None)
        if fn is not None:
            p, a, b = _fn_lines(fn)
            parts.append({"label": f"What it does (Toolbox.t_{name})", "src": src.add(p, a, b)})
            for g in _called(fn, T.Toolbox, inspect.getmodule(fn).__dict__):
                gp, ga, gb = _fn_lines(g)
                parts.append({"label": f"It calls {g.__qualname__}", "src": src.add(gp, ga, gb)})
        head, _, text = s["description"].partition(": ")
        words = _first_sentence(text if kind == "blueprint" and text else s["description"])
        out[kind].append(_item(f"tool:{name}", name, words, parts, sub=head if kind == "blueprint" and text else ""))
    return [("tester", "Chat tools: strategy tester", "What a chat runs in the Strategy Tester: backtests, heat maps, walk-forwards, Monte Carlo, drafts."),
            ("blueprint", "Chat tools: blueprint", "One tool for each phase of the blueprint, saved in the app."),
            ("desk", "Chat tools: desk views", "Read-only views of the live desk, and two safe actions. No tool can trade.")], out


# ---------------------------------------------------------------- skills and scripts

def _frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---", text, re.S)
    out: dict = {}
    for ln in (m.group(1).splitlines() if m else []):
        k, sep, v = ln.partition(":")
        if sep and re.match(r"^[A-Za-z_-]+$", k):
            out[k.strip()] = v.strip().strip("\"'")
    return out


def skills(src: Sources) -> list:
    items, seen = [], set()
    for d in skill_dirs():
        if not d.is_dir():
            continue
        for sd in sorted(d.iterdir()):
            f = sd / "SKILL.md"
            if not f.is_file() or sd.name in seen:
                continue
            seen.add(sd.name)
            fm = _frontmatter(f.read_text(encoding="utf-8", errors="replace"))
            parts = [{"label": "The skill file (SKILL.md)", "src": src.whole(f)}]
            for extra in sorted(x for x in sd.rglob("*") if x.is_file() and x != f and x.suffix in (".py", ".sh", ".json", ".md") and "node_modules" not in x.parts)[:8]:
                parts.append({"label": f"{extra.relative_to(sd)}", "src": src.whole(extra)})
            items.append(_item(f"skill:{sd.name}", fm.get("name", sd.name), _first_sentence(fm.get("description", "")),
                               parts, sub="repo skill" if d.parent.parent == paths.repo_root() else "your skill"))
    return items


def scripts(src: Sources) -> list:
    items = []
    for rel in SCRIPT_DIRS:
        d = paths.repo_root() / rel
        for f in sorted(d.glob("*.py")) if d.is_dir() else []:
            if f.name == "__init__.py":
                continue
            try:
                doc = (ast.get_docstring(ast.parse(f.read_text(encoding="utf-8"))) or "").strip().splitlines()
            except SyntaxError:
                doc = []
            items.append(_item(f"script:{rel}/{f.name}", f.name, _first_sentence(doc[0] if doc else f"{rel}/{f.name}"), [{"label": f.name, "src": src.whole(f)}], sub=rel))
    return items


# ---------------------------------------------------------------- the catalog

def _newest(files) -> tuple:
    fs = [f for f in files if f.is_file()]
    return (max((f.stat().st_mtime_ns for f in fs), default=0), len(fs))


def stamp(research_stamp=None) -> list:
    """What changes when a file the catalog is built from does (newest file time and file count, for each kind): the saved catalog stands until then."""
    root = paths.repo_root()
    sk = [f for d in skill_dirs() if d.is_dir() for f in d.rglob("*") if f.is_file() and "node_modules" not in f.parts]
    return [list(research_stamp) if research_stamp else None, list(_newest((root / "homebase" / "claude_mcp").glob("*.py"))), list(_newest(sk)),
            list(_newest(f for rel in SCRIPT_DIRS for f in (root / rel).glob("*.py")))]


def build(research: Callable[[], dict], research_stamp=None) -> dict:
    """The catalog. `research()` -> {groups, sources, counts} of the research toolkit (`bp.py blockcode`); when it fails, everything else is still here
    and `notes` says what is missing."""
    src, notes, groups = Sources(), [], []
    try:
        r = research()
        groups += r["groups"]
        src.by_id.update(r["sources"])
    except Exception as e:                      # noqa: BLE001 -- a missing toolkit must not hide the other tools
        notes.append(f"The blocks and library are missing: {e}")
    for build_group in (lambda: _chat_groups(src), lambda: [("skills", "Skills", "The Claude skills on this machine: when each is used, and its script.", skills(src)),
                                                              ("scripts", "Scripts", "The repository's own scripts: tools/ and the research toolkit's command line files.", scripts(src))]):
        try:
            for gid, title, words, items in build_group():
                groups.append({"id": gid, "title": title, "words": words, "items": items})
        except Exception as e:                  # noqa: BLE001
            notes.append(f"A part of the arsenal could not be read: {e}")
    return {"groups": groups, "sources": src.by_id, "counts": {g["id"]: len(g["items"]) for g in groups}, "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "stamp": stamp(research_stamp), "notes": notes}


def _chat_groups(src: Sources) -> list:
    heads, items = chat_tools(src)
    return [(gid, title, words, items[gid]) for gid, title, words in heads]


def save(catalog: dict, path=None) -> Path:
    p = Path(path) if path else arsenal_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(catalog), encoding="utf-8")
    os.replace(tmp, p)                          # a reader never sees half a file
    return p


def load(path=None):
    try:
        c = json.loads(Path(path or arsenal_path()).read_text(encoding="utf-8"))
        return c if isinstance(c, dict) and "groups" in c and "sources" in c else None
    except (OSError, ValueError):
        return None


def get(research: Callable[[], dict], research_stamp=None, path=None) -> dict:
    """The saved catalog while its stamp is today's; else a new one, built and saved (not saved when a part of it could not be read)."""
    now = stamp(research_stamp)
    saved = load(path)
    if saved and saved.get("stamp") == now and not saved.get("notes"):
        return saved
    cat = build(research, research_stamp)
    if not cat["notes"]:
        save(cat, path)
    return cat


if __name__ == "__main__":
    from .claude_mcp import blueprint_tools as _BT
    box = _BT.BlueprintMixin()
    cat = get(box.block_code, _BT.toolkit_stamp())
    print(json.dumps({"saved": str(arsenal_path()), "counts": cat["counts"], "notes": cat["notes"]}, indent=1))
    sys.exit(1 if cat["notes"] else 0)
