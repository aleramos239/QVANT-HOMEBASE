"""DRAFT strategies on disk: names, the directory, and file writes. Stdlib only, and it NEVER imports
or executes a draft -- it only reads and writes text.

    <drafts dir> = ~/.homebase/strategies   (HOMEBASE_DRAFTS_DIR overrides it; the test suite always does)
      <name>.py                             one Strategy subclass per file (DRAFT_TEMPLATE below)

A draft's strategy id is "draft_<name>". No built-in strategy id starts with "draft_" (a test pins it),
and a name may not equal a built-in module or strategy name, so a draft can never shadow one.

Who reads what:
  * the Claude MCP server (homebase.claude_mcp) writes/deletes the files through write()/delete();
  * the chart service lists and validates drafts ONLY through homebase.backtest.drafthost, which
    runs them in a child process with a timeout -- a draft is never imported into the service;
  * a backtest child (`runner exec`) runs the source snapshot saved in its own request.json.
The desk (homebase.server / engine / trading) reads its strategies from config.json + homebase.rules
and never looks here (tests/test_claude_tools.py pins that).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ENV = "HOMEBASE_DRAFTS_DIR"
PREFIX = "draft_"
MAX_BYTES = 200_000
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_BUILTIN_DIR = Path(__file__).resolve().parent / "strategies"
# words that would read as something else on the page or in a module path
RESERVED = frozenset({"draft", "drafts", "base", "strategy", "strategies", "test", "tests", "init", "main"})


def drafts_dir() -> Path:
    v = os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "strategies"


def builtin_names() -> frozenset:
    """Every module name in homebase/strategies (read from the directory listing, nothing imported)."""
    try:
        return frozenset(p.stem for p in _BUILTIN_DIR.glob("*.py"))
    except OSError:
        return frozenset()


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


DRAFT_TEMPLATE = '''"""<One line: what this strategy does.>

A DRAFT strategy for the Homebase Strategy Tester. Rules for a valid draft:
  * exactly ONE subclass of homebase.strategies.base.Strategy in the file;
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
