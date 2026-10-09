"""pipe_store.py -- THE PIPELINE'S FILES (pipeline plan A, task 3): one folder an idea, one JSON a stage, and the registry of
every card ever added. It stores what it is given and reads it back: it checks no card (pipe_card.py), runs nothing
(pipe_stages.py) and decides nothing (pipe_runner.py). Nothing here is in git or in the app's own ideas folder.

    <root>/                          the pipeline root = the argument, else HOMEBASE_PIPELINE_ROOT, else ~/.homebase/pipeline
        ideas/<sub-idea>/...         the toolkit's ideas (ideas_root: the root= of every toolkit call, so the Lab is not flooded)
        runs/                        the stores (runs: the out= of every toolkit call); the control pools c1-* / c1o-* are
                                     LINKS to the toolkit's own (research/edge-library/runs_bp): read there, never copied
        runs_test/                   the stores of the ONE read of the unseen days (runs_test: the out= of the toolkit's test)
        p/<name>/card.json           the pipeline card as it was added, + "subs" (its sub-ideas: name, way, bar, toolkit spec)
        p/<name>/state.json          {name, status, stage, stopped_at, why, tries, picked, added_utc, updated_utc, source, family}
        p/<name>/stages/<n>.json     the stage card of stage n, as the stage returned it
        p/<name>/ledger.csv          the idea's own ledger of counted cells (the path only: the toolkit writes it)
        seen.jsonl                   one line a card EVER added: {sig, name, utc}. Never rewritten
        order.jsonl                  the queue: {name, utc, inbox}, one line an add
        pause                        there = the runner stops after the stage in hand
        book/<name>.json             the book card of an idea the owner approved
        runner.lock, runner.log      the runner's (pipe_runner.py)

    root(arg=None) -> Path                              the pipeline root
    add(card, subs, root=None, inbox=False, *, sig, family) -> state
                                                        a CHECKED card with its sub-ideas, its signature and its family
                                                        (pipe_card.check / signature / family_of): card.json, state.json
                                                        "queued", a line on seen.jsonl and on order.jsonl. J.Refuse for a
                                                        name on file, and for a signature seen before under ANY name
    card(name, root=None) -> dict                       card.json (the card + "subs")
    state(name, root=None) -> dict                      state.json; J.Refuse for a name that is not on file
    set_state(name, root=None, **changes) -> state      the state with `changes` over it, updated_utc stamped (always, and
                                                        by the store). A status outside STATUS: ValueError, nothing changed
    write_stage(name, n, card, root=None) -> Path       stages/<n>.json (a stage run again replaces its card)
    reset(name, root=None) -> state                     `bp.py pipe rerun`: the idea starts again from stage 0. Its stage cards are MOVED to
                                                        stages_old/<UTC stamp>/ (never deleted), its state is queued, empty (stage, stopped_at,
                                                        why, picked None; tries 0) and its name goes last in the queue (order.jsonl, not the
                                                        inbox). Refused while it is running, awaits the owner or is in the book. The card,
                                                        the stores (runs/), the ledger and seen.jsonl are not touched
    stages(name, root=None) -> {n: card}                every stage card on file, by stage number
    order(root=None) -> [names]                         the queue: the ideas whose status is queued or running, the inbox's
                                                        first, then by the time they were added
    ideas(root=None) -> [states]                        every idea's state, as added
    paused(root=None) / pause(root=None) / resume(root=None) -> bool        the pause file: is it there / put it / take it away
    ideas_root(root=None) -> Path                       <root>/ideas, made
    runs(root=None, pools=None) -> Path                 <root>/runs, made, with a link for every control pool of `pools`
                                                        (default: pools()) that has nothing under its name there yet
    pools() -> Path                                     the toolkit's stores folder (runner.RUNS)
    runs_test(root=None) -> Path                        <root>/runs_test, made: where an idea's read of the unseen days is
                                                        written (never the toolkit's own runs_bp_test)
    ledger(name, root=None) -> Path                     p/<name>/ledger.csv
    book(root=None) -> [book cards]                     by name
    write_book(name, card, root=None) -> Path           book/<name>.json

HOW IT WRITES. A JSON file is written whole or not at all: a temp file beside it, flushed to the disk, then put in its
place (a reader never sees half a file; a write that dies leaves the old one). A line on a .jsonl is appended under an
exclusive lock on that file and is on the disk before the call returns. An idea's folder appears whole (it is made under a
temp name and renamed), and a change of a state is one read-change-write at a time across processes (the runner and a
command may both write). add() holds seen.jsonl's lock from its checks to its line: two adds never both pass.
An add that is KILLED between the folder and its seen line leaves an idea that is on file and gets its turn (order() reads
the states, not only order.jsonl) but whose signature is not registered: the gentler of the two half-states.
The numbers of the toolkit (numpy's) are saved as plain JSON. Standard library only (pools() alone imports the runner, and
only when it is asked). Locked by tests/test_pipe_store.py.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path

import judge as J

ENV = "HOMEBASE_PIPELINE_ROOT"
NAME = re.compile(r"^[a-z][a-z0-9_]{1,33}$")       # a pipeline card's name (the plan's shapes): it is a folder's name here
STATUS = ("queued", "running", "stopped", "code_problem", "awaiting_owner", "book", "refused")
LIVE = ("queued", "running")                        # what the runner still has work on
POOLS = ("c1-*", "c1o-*")                           # the control pools of the toolkit's stores folder: the random entries, and those of the open table
SEEN, ORDER, PAUSE = "seen.jsonl", "order.jsonl", "pause"


def root(arg=None) -> Path:
    """The pipeline root: the argument, else the environment, else the app's own folder (the tests never get that far)."""
    v = arg or os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "pipeline"


_at = root                                          # (every function below takes a `root` of its own)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _plain(o):
    """The toolkit's numbers are numpy's: as plain JSON values. Anything else is refused."""
    if hasattr(o, "tolist"):
        return o.tolist()
    if isinstance(o, os.PathLike):
        return os.fspath(o)
    raise TypeError(f"{type(o).__name__} is not JSON")


def _write(path: Path, data) -> Path:
    """A JSON file, whole or not at all: a temp file beside it, on the disk, then in its place."""
    text = json.dumps(data, indent=1, ensure_ascii=False, default=_plain) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def _json(path: Path):
    """A saved JSON object, or None when the file is missing or does not read as one."""
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


@contextmanager
def _log(path: Path):
    """A .jsonl, open to append and locked: one writer at a time, across processes. -> (the file, its text so far)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        yield f, f.read()


def _append(f, text: str, rec: dict) -> dict:
    """One line, never rewriting an earlier one, on the disk before the call returns."""
    f.write(("" if not text or text.endswith("\n") else "\n") + json.dumps(rec, ensure_ascii=False, default=_plain) + "\n")
    f.flush()
    os.fsync(f.fileno())
    return rec


def _lines(path: Path) -> list:
    """The lines of a .jsonl that read as objects, with their line numbers: [(n, record | None)] (None = it does not read)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return _parse(text)


def _parse(text: str) -> list:
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip():
            try:
                rec = json.loads(line)
            except ValueError:
                rec = None
            out.append((n, rec if isinstance(rec, dict) else None))
    return out


def _name(name) -> str:
    if not isinstance(name, str) or not NAME.match(name):
        raise J.Refuse(f"{name!r} is no pipeline card's name (a small letter, then 1 to 33 small letters, digits or _)")
    return name


def _dir(name, root) -> Path:
    d = _at(root) / "p" / _name(name)
    if not (d / "state.json").is_file():
        raise J.Refuse(f"no pipeline idea {name!r} under {_at(root)}")
    return d


@contextmanager
def _locked(d: Path):
    """One read-change-write of an idea's state at a time, across processes."""
    with open(d / ".lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


# ---------------------------------------------------------------- an idea

def add(card: dict, subs: list, root=None, inbox: bool = False, *, sig: str, family: str) -> dict:
    """File a checked card: its folder (card.json with its sub-ideas, state.json "queued"), then its line on seen.jsonl
    and on order.jsonl. -> the state. Refused: a name on file; a signature seen before, under any name."""
    r, name = _at(root), _name(card.get("name"))
    with _log(r / SEEN) as (seen, text):
        d = r / "p" / name
        if d.exists():
            was = _json(d / "state.json") or {}
            raise J.Refuse(f"a pipeline card named {name!r} is already on file (added {was.get('added_utc', 'at a time not on file')}, "
                           f"status {was.get('status', 'not on file')}): give the new card another name")
        for n, rec in _parse(text):
            if rec is None:
                raise J.Refuse(f"{r / SEEN} holds a line that does not read (line {n}): mend it first -- it is the list of every card "
                               "ever added, and a card is not taken as new on a list that cannot be read")
            if rec.get("sig") == sig:
                raise J.Refuse(f"{name!r} is the same card as {rec.get('name')!r}, added {rec.get('utc')}: the same market, session, sides and "
                               "ways under another name are the same card, and a card is run once")
        now = _now()
        st = {"name": name, "status": "queued", "stage": None, "stopped_at": None, "why": "", "tries": 0, "picked": None,
              "added_utc": now, "updated_utc": now, "source": card.get("source"), "family": family}
        tmp = d.with_name(f".{name}.{os.getpid()}.tmp")                # the folder appears whole, or not at all
        try:
            (tmp / "stages").mkdir(parents=True)
            _write(tmp / "card.json", {**card, "subs": subs})
            _write(tmp / "state.json", st)
            os.rename(tmp, d)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        _append(seen, text, {"sig": sig, "name": name, "utc": now})
    with _log(r / ORDER) as (f, text):
        _append(f, text, {"name": name, "utc": now, "inbox": bool(inbox)})
    return st


def card(name, root=None) -> dict:
    """The card as it was added, with its sub-ideas under "subs"."""
    return json.loads((_dir(name, root) / "card.json").read_text(encoding="utf-8"))


def state(name, root=None) -> dict:
    return json.loads((_dir(name, root) / "state.json").read_text(encoding="utf-8"))


def set_state(name, root=None, **changes) -> dict:
    """The state with `changes` over it; updated_utc is the store's stamp, whatever the changes say."""
    if "status" in changes and changes["status"] not in STATUS:
        raise ValueError(f"{changes['status']!r} is no status of a pipeline idea ({', '.join(STATUS)})")
    d = _dir(name, root)
    with _locked(d):
        st = {**json.loads((d / "state.json").read_text(encoding="utf-8")), **changes, "name": name, "updated_utc": _now()}
        _write(d / "state.json", st)
    return st


def owner_pick(name, root=None):
    """The box the owner named for an idea (`p/<name>/owner_pick.json`: {cell, why, utc}), or None."""
    f = _dir(name, root) / "owner_pick.json"
    try:
        got = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) and isinstance(got.get("cell"), str) and got["cell"] else None


def set_owner_pick(name, cell, why, root=None) -> dict:
    """The owner names the box stage 1 picks for `name` (2026-10-09; never a chat tool). It must still be one of the boxes at the floor of the
    best map: stage 1 checks that. Kept across `rerun`. Refused: no cell, no reason."""
    if not (isinstance(cell, str) and cell.strip()):
        raise J.Refuse("pipe pick: the cell (the box's id, e.g. k0p4_pts45-r2) is needed")
    if not (isinstance(why, str) and why.strip()):
        raise J.Refuse("pipe pick: say why (--why=TEXT): the reason is kept with the idea")
    d = _dir(name, root)
    got = {"cell": cell.strip(), "why": " ".join(why.split()), "utc": _now()}
    _write(d / "owner_pick.json", got)
    return got


def clear_owner_pick(name, root=None) -> bool:
    f = _dir(name, root) / "owner_pick.json"
    if f.exists():
        f.unlink()
        return True
    return False


def reset(name, root=None) -> dict:
    """The idea starts again from stage 0 (module docstring) -> its state."""
    r, d = _at(root), _dir(name, root)
    with _locked(d):
        st = json.loads((d / "state.json").read_text(encoding="utf-8"))
        why = {"running": "is running (the runner works on it, or died in a stage)", "awaiting_owner": "waits for the owner's look",
               "book": "is in the book"}.get(st.get("status"))
        if why:
            raise J.Refuse(f"{name} {why}: an idea is run again only after it stopped (or was refused); nothing was moved")
        now, cards = _now(), sorted(p for p in (d / "stages").glob("*") if p.is_file())
        if cards:
            stamp = dt.datetime.fromisoformat(now).astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            to, k = d / "stages_old" / stamp, 1
            while to.exists():                       # two re-runs in one second keep both sets
                k += 1
                to = d / "stages_old" / f"{stamp}-{k}"
            to.mkdir(parents=True)
            for p in cards:
                os.replace(p, to / p.name)
        st = {**st, "status": "queued", "stage": None, "stopped_at": None, "why": None, "tries": 0, "picked": None, "name": name, "updated_utc": now}
        _write(d / "state.json", st)
    with _log(r / ORDER) as (f, text):
        _append(f, text, {"name": name, "utc": now, "inbox": False})
    return st


def write_stage(name, n, card, root=None) -> Path:
    return _write(_dir(name, root) / "stages" / f"{int(n)}.json", card)


def stages(name, root=None) -> dict:
    got = {int(p.stem): _json(p) for p in (_dir(name, root) / "stages").glob("*.json") if p.stem.isdigit()}
    return {n: got[n] for n in sorted(got) if got[n] is not None}


def ledger(name, root=None) -> Path:
    return _dir(name, root) / "ledger.csv"


# ---------------------------------------------------------------- every idea, the queue, the pause

def ideas(root=None) -> list:
    """Every idea's state, as added (a folder without a state that reads is no idea)."""
    got = [_json(p) for p in (_at(root) / "p").glob("*/state.json") if NAME.match(p.parent.name)]
    return sorted((s for s in got if s), key=lambda s: (str(s.get("added_utc")), str(s.get("name"))))


def order(root=None) -> list:
    """The queue: the names that are queued or running, the inbox's first, then by the time they were added (a name's
    LATEST line on order.jsonl is its place; an idea without a line comes last, by its added_utc)."""
    place = {}
    for n, rec in _lines(_at(root) / ORDER):
        if rec and "name" in rec:
            place[rec["name"]] = (not rec.get("inbox"), n)
    last = (True, float("inf"))
    return [s["name"] for s in sorted((s for s in ideas(root) if s.get("status") in LIVE), key=lambda s: place.get(s["name"], last))]


def paused(root=None) -> bool:
    return (_at(root) / PAUSE).exists()


def pause(root=None) -> bool:
    """Put the pause file: the runner stops after the stage in hand. -> True."""
    if not paused(root):
        _write(_at(root) / PAUSE, {"utc": _now()})
    return paused(root)


def resume(root=None) -> bool:
    """Take the pause file away. -> False."""
    (_at(root) / PAUSE).unlink(missing_ok=True)
    return paused(root)


# ---------------------------------------------------------------- the toolkit's two folders

def ideas_root(root=None) -> Path:
    """The ideas root of every toolkit call the pipeline makes (root=, HOMEBASE_IDEAS_ROOT): never the app's own."""
    d = _at(root) / "ideas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pools() -> Path:
    """The toolkit's own stores folder, where the control pools were built (runner.RUNS)."""
    from . import runner as RUN                     # (the runner brings numpy and the engine: only when the real folder is asked for)
    return RUN.RUNS


def _pool_home() -> Path:
    return pools()                                  # (runs() takes a `pools` of its own; read when called, so a test can set it)


def runs(root=None, pools=None) -> Path:
    """The stores folder of every toolkit call the pipeline makes (out=), with the control pools of `pools` LINKED in: a
    pool is read where it was built, never copied, and what already stands under a pool's name here is left as it is."""
    out = _at(root) / "runs"
    out.mkdir(parents=True, exist_ok=True)
    src = Path(pools) if pools is not None else _pool_home()
    for pool in sorted(p for pat in POOLS for p in src.glob(pat) if p.is_dir()):
        link = out / pool.name
        if not os.path.lexists(link):
            try:
                os.symlink(pool.resolve(), link, target_is_directory=True)
            except FileExistsError:                 # another process linked it between the look and the link
                pass
    return out


def runs_test(root=None) -> Path:
    """The stores folder of the ONE read of the unseen days (the out= of the toolkit's test): the pipeline's own, never the
    toolkit's runs_bp_test. No pool is linked there: a read writes its own random-entry pool beside its two tables."""
    out = _at(root) / "runs_test"
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------- the book

def book(root=None) -> list:
    """The book cards, by name."""
    got = [_json(p) for p in sorted((_at(root) / "book").glob("*.json")) if NAME.match(p.stem)]
    return [c for c in got if c is not None]


def write_book(name, card, root=None) -> Path:
    return _write(_at(root) / "book" / f"{_name(name)}.json", card)
