"""DRAFT strategies on disk: names, the directory, and file writes. Stdlib only, and it NEVER imports
or executes a draft -- it only reads and writes text.

    <drafts dir> = ~/.homebase/strategies   (HOMEBASE_DRAFTS_DIR overrides it; the test suite always does)
      <name>.py                             one Strategy subclass per file (DRAFT_TEMPLATE below)

A draft's strategy id is "draft_<name>". No built-in strategy id starts with "draft_" (a test pins it),
and a name may not equal a built-in module or strategy name, so a draft can never shadow one.

Who reads what:
  * the Claude MCP server (homebase.claude_mcp) writes/deletes the files through write()/delete();
  * the chart service LISTS and VALIDATES drafts from static_meta() alone -- an AST read of the text: no
    draft code runs to list the catalog, read a strategy or validate a request;
  * the only place a draft's code ever runs is its backtest child (`runner exec`), launched inside the
    macOS sandbox (homebase/backtest/sandbox.py + draft.sb) with the source snapshot saved in its
    request.json.
A name may not shadow a stdlib or homebase module (and the drafts dir is never put on any sys.path).
The desk (homebase.server / engine / trading) reads its strategies from config.json + homebase.rules
and never looks here (tests/test_claude_drafts.py pins that).
"""
from __future__ import annotations

import ast
import os
import re
import sys
import time
from pathlib import Path

ENV = "HOMEBASE_DRAFTS_DIR"
PREFIX = "draft_"
MAX_BYTES = 200_000
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_BUILTIN_DIR = Path(__file__).resolve().parent / "strategies"
# words that would read as something else on the page or in a module path
RESERVED = frozenset({"draft", "drafts", "base", "strategy", "strategies", "test", "tests", "init", "main",
                      "homebase", "sitecustomize", "usercustomize", "conftest", "setup"})
_HOMEBASE_DIR = Path(__file__).resolve().parent
# Python 3.10+ lists its stdlib; the MCP server may run on an older python3, which gets this floor instead
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ())) | frozenset(sys.builtin_module_names) | frozenset({
    "abc", "ast", "asyncio", "base64", "bisect", "builtins", "calendar", "cmath", "code", "collections", "copy",
    "csv", "ctypes", "dataclasses", "datetime", "decimal", "email", "enum", "fcntl", "fractions", "functools",
    "gc", "glob", "gzip", "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect", "io", "itertools",
    "json", "logging", "math", "operator", "os", "pathlib", "pickle", "platform", "queue", "random", "re",
    "resource", "secrets", "select", "shutil", "signal", "site", "socket", "sqlite3", "ssl", "stat",
    "statistics", "string", "struct", "subprocess", "sys", "tempfile", "threading", "time", "token", "tokenize",
    "traceback", "types", "typing", "unittest", "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
    "zoneinfo", "array", "numbers", "contextlib", "textwrap", "argparse", "codecs", "locale", "posix", "errno"})


def drafts_dir() -> Path:
    v = os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "strategies"


def builtin_names() -> frozenset:
    """Every module name in homebase/strategies (read from the directory listing, nothing imported)."""
    try:
        return frozenset(p.stem for p in _BUILTIN_DIR.glob("*.py"))
    except OSError:
        return frozenset()


_SHADOW: tuple[float, frozenset] | None = None
_SHADOW_TTL = 60.0


def shadow_names() -> frozenset:
    """Module names a draft file must never be called: the stdlib's and every homebase module/package, so a
    stray PYTHONPATH (or a cwd of the drafts dir) could never make an import pick up a draft.
    Walking the package is slow (it holds the service's state directory), and listing N drafts asked for it N
    times: the answer is kept for a minute."""
    global _SHADOW
    now = time.monotonic()
    if _SHADOW is not None and now - _SHADOW[0] < _SHADOW_TTL:
        return _SHADOW[1]
    _SHADOW = (now, _shadow_names())
    return _SHADOW[1]


def _shadow_names() -> frozenset:
    try:
        mine = {p.stem for p in _HOMEBASE_DIR.rglob("*.py")} | {p.name for p in _HOMEBASE_DIR.rglob("*")
                                                                if p.is_dir()}
    except OSError:
        mine = set()
    return _STDLIB | frozenset(mine)


def is_draft_id(sid) -> bool:
    return isinstance(sid, str) and sid.startswith(PREFIX)


def draft_id(name: str) -> str:
    return PREFIX + name


def name_of(sid: str) -> str:
    """"draft_foo" -> "foo" (validated)."""
    if not is_draft_id(sid):
        raise ValueError(f"{sid!r} is not a draft strategy id (draft ids start with {PREFIX!r})")
    return validate_name(sid[len(PREFIX):])


def validate_name(name, builtin_ids=()) -> str:
    """A draft name: lowercase letters, digits and '_' (2-40 chars, a letter first), not a built-in
    strategy's module or id, not reserved, not itself starting with 'draft_'. ValueError otherwise."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError("name: 2-40 characters of a-z, 0-9 and '_', starting with a letter "
                         "(e.g. nq_orb_15)")
    if name.startswith(PREFIX) or name in RESERVED:
        raise ValueError(f"name: {name!r} is reserved")
    if name in builtin_names() or name in set(builtin_ids) or draft_id(name) in set(builtin_ids):
        raise ValueError(f"name: {name!r} is a built-in strategy -- pick another name")
    if name in shadow_names():
        raise ValueError(f"name: {name!r} is a Python or homebase module name -- pick another name")
    return name


def path_for(name: str, base: Path | None = None) -> Path:
    base = Path(base) if base is not None else drafts_dir()
    return base / f"{validate_name(name)}.py"


def list_files(base: Path | None = None) -> list[tuple[str, Path]]:
    """[(name, path)] for every validly named <name>.py in the drafts dir (others are ignored)."""
    base = Path(base) if base is not None else drafts_dir()
    out = []
    try:
        entries = sorted(base.glob("*.py"))
    except OSError:
        return out
    for p in entries:
        try:
            validate_name(p.stem)
        except ValueError:
            continue
        if p.is_file() and not p.is_symlink():
            out.append((p.stem, p))
    return out


def read(name: str, base: Path | None = None) -> str:
    p = path_for(name, base)
    if not p.is_file():
        raise FileNotFoundError(f"no draft {name!r}")
    return p.read_text(encoding="utf-8")


def check_source(code) -> None:
    """Text checks only (size, a syntax parse via compile() -- which never runs the code)."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code: the draft's Python source")
    if len(code.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"code: at most {MAX_BYTES:,} bytes")
    try:
        compile(code, "<draft>", "exec", dont_inherit=True)
    except SyntaxError as e:
        raise ValueError(f"SyntaxError: {e.msg} (line {e.lineno})") from None
    except (MemoryError, RecursionError, ValueError) as e:     # a pathological source (parser stack overflow)
        raise ValueError(f"the source could not be parsed: {type(e).__name__}") from None
    static_meta(code)                                           # ValueError when the catalog could not read it


def write(name: str, code: str, base: Path | None = None, builtin_ids=()) -> Path:
    """Write <name>.py atomically. Never anything but that one file in the drafts dir."""
    validate_name(name, builtin_ids)
    check_source(code)
    base = Path(base) if base is not None else drafts_dir()
    base.mkdir(parents=True, exist_ok=True)
    p = path_for(name, base)
    if p.is_symlink():
        raise ValueError(f"{p} is a symlink: refusing to write through it")
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(code, encoding="utf-8")
    os.replace(tmp, p)
    return p


def delete(name: str, base: Path | None = None) -> bool:
    p = path_for(name, base)
    if p.is_symlink() or not p.exists():
        return False
    p.unlink()
    return True


# ---------------------------------------------------------------- static metadata (never runs the code)

_CLASS_ATTRS = {"name": str, "root": str, "session_window": (tuple, list), "bar_minutes": int,
                "bar_window": (tuple, list, type(None)), "placement_ms": int, "session_independent": bool}
INPUT_FIELDS = ("key", "label", "type", "default", "min", "max", "step", "choices")


class StaticError(ValueError):
    """The draft's catalog metadata cannot be read from its text alone."""


def _lit(node, what: str):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        raise StaticError(f"{what} must be a literal (a number, string, bool, None, tuple or list), "
                          f"not an expression: the catalog reads drafts without running them") from None


def _is_strategy_base(b) -> bool:
    return (isinstance(b, ast.Name) and b.id == "Strategy") or (isinstance(b, ast.Attribute) and b.attr == "Strategy")


def _input(call, i: int) -> dict:
    if not (isinstance(call, ast.Call) and ((isinstance(call.func, ast.Name) and call.func.id == "Input")
                                            or (isinstance(call.func, ast.Attribute) and call.func.attr == "Input"))):
        raise StaticError(f"inputs(): item {i} must be an Input(...) call")
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        raise StaticError(f"inputs(): item {i}: no *args / **kwargs")
    if len(call.args) > len(INPUT_FIELDS):
        raise StaticError(f"inputs(): item {i}: too many arguments")
    d = {INPUT_FIELDS[j]: _lit(a, f"inputs() item {i} argument {j + 1}") for j, a in enumerate(call.args)}
    for k in call.keywords:
        if k.arg not in INPUT_FIELDS or k.arg in d:
            raise StaticError(f"inputs(): item {i}: unknown or repeated argument {k.arg!r}")
        d[k.arg] = _lit(k.value, f"inputs() item {i} {k.arg}")
    for need in ("key", "label", "type", "default"):
        if need not in d:
            raise StaticError(f"inputs(): item {i} needs {need}")
    d["choices"] = list(d.get("choices") or ())
    return d


def static_meta(source: str) -> dict:
    """The draft's catalog metadata from its SOURCE TEXT (ast only -- nothing is imported or run):
    {class, doc, name, root, session_window, bar_minutes, ..., inputs: [{key, label, type, default, min, max,
    step, choices}]}. The draft must define exactly one class deriving directly from Strategy, whose class
    attributes above are literals and whose inputs() (when it has one) is `return [Input(...), ...]` with
    literal arguments -- the shape DRAFT_TEMPLATE shows. StaticError (a ValueError) otherwise."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise StaticError(f"SyntaxError: {e.msg} (line {e.lineno})") from None
    except (MemoryError, RecursionError, ValueError) as e:
        raise StaticError(f"the source could not be parsed: {type(e).__name__}") from None
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and any(_is_strategy_base(b) for b in n.bases)]
    if len(classes) != 1:
        raise StaticError(f"a draft defines exactly one class deriving from Strategy at the top level "
                          f"(found {len(classes)})")
    cls = classes[0]
    meta = {"class": cls.name, "doc": ast.get_docstring(tree) or ast.get_docstring(cls) or "", "inputs": []}
    for st in cls.body:
        targets = st.targets if isinstance(st, ast.Assign) else [st.target] if isinstance(st, ast.AnnAssign) else []
        for t in targets:
            if isinstance(t, ast.Name) and t.id in _CLASS_ATTRS and st.value is not None:
                v = _lit(st.value, t.id)
                if not isinstance(v, _CLASS_ATTRS[t.id]) or (t.id == "bar_minutes" and isinstance(v, bool)):
                    raise StaticError(f"{t.id}: wrong type ({type(v).__name__})")
                meta[t.id] = list(v) if isinstance(v, (tuple, list)) else v
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)) and st.name == "inputs":
            body = [b for b in st.body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
            if len(body) != 1 or not isinstance(body[0], ast.Return) or \
                    not isinstance(body[0].value, (ast.List, ast.Tuple)):
                raise StaticError("inputs() must be a single `return [Input(...), ...]` with literal arguments")
            meta["inputs"] = [_input(c, i) for i, c in enumerate(body[0].value.elts)]
    if not meta.get("root"):
        raise StaticError('the strategy needs a literal `root = "NQ"` (or another archive root)')
    if "session_window" in meta and len(meta["session_window"]) != 2:
        raise StaticError("session_window: (start, end)")
    return meta


DRAFT_TEMPLATE = '''"""<One line: what this strategy does.>

A DRAFT strategy for the Homebase Strategy Tester. Rules for a valid draft:
  * exactly ONE class deriving directly from Strategy in the file;
  * the catalog reads the class WITHOUT running it: `name`, `root`, `session_window`, `bar_minutes`,
    `session_independent` are literals, and inputs() is exactly `return [Input(...), ...]` with literal
    arguments (Input(key, label, type, default, min, max, step, choices));
  * the code runs only in the backtest, inside a sandbox: no network, no files but its own run dir,
    at most 20 minutes of wall clock;
  * absolute imports only (from homebase.strategies.base import Input, Strategy);
    stdlib only -- no numpy/pandas;
  * the file name is the draft's name; its tester id is "draft_<name>" (the class's own `id` is
    overwritten with it), so `id` below is informational;
  * `root` is a futures root the tick archive has (NQ, ES, YM, RTY, GC, SI, CL, ...);
  * all times are America/New_York wall clock, "HH:MM" or "HH:MM:SS";
  * events run BEFORE the first print at or after their time: on_session(ctx) at session_window[0],
    on_bar(ctx, bar) at each bar close when bar_minutes > 0 (bar.o/h/l/c/v, bar.start_ns/end_ns),
    on_time(ctx, et_time) at every time listed in times();
  * orders (side is "long" | "short"; price, sl and tp are ABSOLUTE prices, rounded to the tick):
    ctx.stop_entry(side, price, qty=None, sl=None, tp=None, tp_rr=None) / ctx.limit_entry(...same) /
    ctx.market(side, qty=None, sl=None, tp=None, tp_rr=None, ref=None) -> Order; ctx.oco(a, b);
    ctx.cancel(order); ctx.flatten(reason="time"); ctx.move_brackets_to_fill = True (re-price SL/TP
    from the actual fill); ctx.plot(name, t_ns, value); ctx.hline(name, price, role=
    "anchor"|"entry"|"sl"|"tp"|"level"); ctx.skip(reason);
  * reads: ctx.last_price (last print before now, or None), ctx.now_ns, ctx.flat, ctx.tick,
    ctx.point_value, ctx.qty, ctx.date, ctx.daily (prior daily bars, when needs_daily() returns True).
    homebase/backtest/engine.py (class Ctx) has the exact signatures and the fill law
    (stops fill at the stop or worse + slippage; a bar spanning SL and TP fills the SL);
  * set session_independent = True only if every session's state resets in on_session (the
    walk-forward refuses a strategy without it).
"""
from __future__ import annotations

from homebase.strategies.base import Input, Strategy


class MyDraft(Strategy):
    id = "draft_my_draft"             # overwritten with draft_<file name>
    name = "My draft"
    root = "NQ"
    session_window = ("09:25", "16:00")   # ET [start, end) the tape must cover
    session_independent = True

    @classmethod
    def inputs(cls):
        return [Input("offset_pts", "Offset (pts)", "float", 10.0, 0.25, 100, 0.25),
                Input("sl_pts", "Stop (pts)", "float", 5.0, 0.25, 100, 0.25),
                Input("tp_pts", "Target (pts)", "float", 15.0, 0.25, 400, 0.25)]

    def times(self):
        return ["09:30:00", "15:55"]

    def on_session(self, ctx):
        self.done = False

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            px = ctx.last_price
            if px is None:
                ctx.skip("no print before 09:30")
                return
            off, sl, tp = self.p["offset_pts"], self.p["sl_pts"], self.p["tp_pts"]
            ctx.hline("anchor", px, role="anchor")
            ctx.move_brackets_to_fill = True
            up, dn = px + off, px - off
            long_ = ctx.stop_entry("long", up, sl=up - sl, tp=up + tp)
            short = ctx.stop_entry("short", dn, sl=dn + sl, tp=dn - tp)
            ctx.oco(long_, short)
        elif et_time == "15:55":
            ctx.flatten("time")
'''
