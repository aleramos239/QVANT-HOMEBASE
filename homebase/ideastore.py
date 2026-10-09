"""Blueprint ideas on disk: one folder per strategy idea, the status read off its saved results, the one-read
log of the test days, and the idea's record in the Lab. Stdlib only (the research toolkit imports it with its
own Python, 3.9), and it never runs anything: it reads and writes text.

    <ideas root> = ~/.homebase/ideas    (HOMEBASE_IDEAS_ROOT or a `root` argument overrides it; the test suite
                                         always does)
      test_reads.jsonl                  the one-read log: append only, under a file lock, synced to disk
      <name>/
        idea.json                       status, phase, round, pass/fail lines, next step, early look, run ids,
                                        Lab group
        card.md  spec.json  check.json  phase 0 (the card, the settings) and phase 1 (the code check)
        rounds/<n>/reason.txt  spec.json  build.json      phase 2: n = 1..5, the reason saved BEFORE the run
        lock.json  test.json  sim/<account>.json  eval.json      phases 3 to 6
        early_look/lock.json  test.json an early look at the test days: the toolkit's own files, beside the
                                        idea's and never among them (not its lock, not its test)
        log.jsonl                       one line per event
    <drafts dir>/<name>.py              the idea's Lab draft (homebase.draftstore): its card and latest verdict
                                        in a marked comment block on top. An idea folder that was moved never
                                        writes the real Lab: it is told its drafts dir too (lab_dir)

The format is the blueprint toolkit's plan (research/edge-library/out/blueprint/toolkit_plan.md, section 3). A
result file holds one command's result as the toolkit prints it (section 8); what is read here is its `lines`:
[{"line": "2.2", "passed": true | false | null, "text": "2.2 FAIL average trade $41 (need $70)"}, ...].

THE STATUS IS NEVER SET. It is read off the saved results, every time (status(); idea.json only mirrors it).
A phase is passed when every line the law has for it is in the result and none failed (BLUEPRINT.md section 2:
"a phase is passed only when every line is true"; passed null = the line does not apply, which is no failure):
    idea                until the build passes
    lead                every 2.x line passed in the latest finished round
    proven_on_history   a lead whose test.json passed every 4.x line
    proven_live         ... and whose eval.json passed every 6.x line, with 6.1 to 6.5 (the lines read on live
                        trades) each TRUE: "not read yet" is never a pass
    shelved             not passed after round 5, or a finished test that did not pass (NOT PROVEN: it is not
                        re-tuned and re-tested)
A result that was refused, is a dry run, or is still running never counts.
Nor does an EARLY LOOK: the test days read for an idea that is not locked, on the owner's yes (his decision of
2026-10-06). Its result says "early_look": true. The toolkit keeps it beside the idea's own files
(early_look/test.json), where no status is read; and a test.json that says so is not counted either. It
proves nothing and it shelves nothing: the idea keeps the status, the phase and the verdict its build gives it.
idea.json says that one is on file (`early_look`), and so does the first line of the Lab block. A later
test.json that is not an early look counts as any test does.

Who writes what: the toolkit (research/edge-library/bp.py) saves each phase with the write_* functions; the
connector (homebase.claude_mcp.blueprint_tools) calls sync() after every command, which brings idea.json, the
block on the Lab draft and the draft's Lab group up to date. The desk reads none of it.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

from . import draftstore

ENV = "HOMEBASE_IDEAS_ROOT"
READS_FILE = "test_reads.jsonl"
STATUSES = ("idea", "lead", "proven_on_history", "proven_live", "shelved")
GROUPS = {"idea": "Ideas", "lead": "Leads", "proven_on_history": "Proven on history",
          "proven_live": "Proven live", "shelved": "Shelved"}        # the Lab group of an idea's draft, by status
MAX_ROUNDS = 5                                                        # line 2.9
LINES = {2: tuple(f"2.{i}" for i in range(1, 10)), 4: tuple(f"4.{i}" for i in range(1, 10)),
         6: tuple(f"6.{i}" for i in range(1, 10))}                    # the law's lines of the phases a status hangs on (law v1.1: 4.8, 4.9, 6.9)
LIVE_LINES = ("6.1", "6.2", "6.3", "6.4", "6.5")                      # read on live trades: each must be TRUE
READ_STATES = ("claimed", "judged")
EARLY_LOOK = "early_look"                                             # an early look's folder, and its result's mark
BLOCK_START = "# >>> BLUEPRINT RECORD"
BLOCK_END = "# <<< BLUEPRINT RECORD"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@:-]{0,119}$")        # an account or a run id: one safe file-name part
_ROOT_RE = re.compile(r"^[A-Z0-9]{1,6}$")
RECORD_STUB = '''"""Blueprint record of the idea {name}: its card and latest verdict are in the block above.

A record does not trade in the tester: the idea runs in the research engine, through the blueprint tools.
When the idea is ported to the tester, the strategy replaces the class below and the block stays on top."""
from __future__ import annotations

from homebase.strategies.base import Strategy


class Record(Strategy):
    name = "{name} (blueprint record)"
    root = "{root}"
    session_independent = True
'''


class ReadOnFile(ValueError):
    """The test days were already read for this idea: the read is not repeated."""


class ReadLogUnreadable(ValueError):
    """test_reads.jsonl holds a line that does not read. It is refused, never read as "no read on file"."""


def ideas_root(root=None) -> Path:
    if root is not None:
        return Path(root)
    v = os.environ.get(ENV)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "ideas"


def validate_name(name) -> str:
    """An idea is named like its Lab draft, <name>.py (draftstore.validate_name). ValueError otherwise."""
    return draftstore.validate_name(name)


def idea_dir(name, root=None) -> Path:
    return ideas_root(root) / validate_name(name)


def exists(name, root=None) -> bool:
    return idea_dir(name, root).is_dir()


def _dir(name, root=None) -> Path:
    d = idea_dir(name, root)
    if not d.is_dir():
        raise FileNotFoundError(f"no idea {name!r}")
    return d


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _plain(o):
    """The toolkit's numbers are numpy's: as plain JSON values. Anything else is refused."""
    if hasattr(o, "tolist"):
        return o.tolist()
    if isinstance(o, os.PathLike):
        return os.fspath(o)
    raise TypeError(f"{type(o).__name__} is not JSON")


def _dumps(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=_plain) + "\n"


def _write(path: Path, text: str) -> Path:
    """Atomically: a temp file beside it, then a replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def _json(path: Path):
    """A saved JSON object, or None when the file is missing or does not read as one."""
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


@contextmanager
def _locked(d: Path):
    """One read-change-write of an idea's idea.json at a time, across processes: the toolkit's job and the
    connector both bring it up to date."""
    with open(d / ".lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


# ---------------------------------------------------------------- the idea folder

def create(name, root=None, exist_ok: bool = False) -> dict:
    """A new idea: its folder and its first idea.json (status idea, phase 0). FileExistsError when it is
    there already, unless exist_ok."""
    d = idea_dir(name, root)
    if d.is_dir():
        if not exist_ok:
            raise FileExistsError(f"there is already an idea {name!r}")
        return _refresh(d)
    d.mkdir(parents=True)
    _log(d, "created")
    return _refresh(d)


def _put(name, rel: str, data, root) -> Path:
    """Save one file of an idea (text as it is, a dict as JSON), then bring idea.json up to date with it."""
    d = _dir(name, root)
    p = _write(d / rel, data if isinstance(data, str) else _dumps(data))
    _refresh(d)
    return p


def _object(data, what: str) -> dict:
    if not isinstance(data, dict):
        raise ValueError(f"{what}: expected a JSON object")
    return data


def write_card(name, text, root=None) -> Path:
    """card.md: the idea card, written before any run (phase 0)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("card: the idea card's text")
    return _put(name, "card.md", text, root)


def write_spec(name, spec, root=None) -> Path:
    """spec.json: {name, version, card, run} (phase 0)."""
    return _put(name, "spec.json", _object(spec, "spec"), root)


def write_check(name, result, root=None) -> Path:
    """check.json: the code check's result (lines 1.1-1.6)."""
    return _put(name, "check.json", _object(result, "check"), root)


def _round(n) -> int:
    if type(n) is not int or not 1 <= n <= MAX_ROUNDS:
        raise ValueError(f"round: 1 to {MAX_ROUNDS} (the blueprint allows at most {MAX_ROUNDS} rounds: line 2.9)")
    return n


def write_reason(name, n, text, root=None) -> Path:
    """rounds/<n>/reason.txt: why this round is run, saved BEFORE it runs (line 2.9) -- so never again once
    the round has its result."""
    _round(n)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("reason: a sentence or two on why this round is run, written before it runs")
    if (_dir(name, root) / "rounds" / str(n) / "build.json").exists():
        raise ValueError(f"round {n} has its result: its reason stays as it was written before the run")
    return _put(name, f"rounds/{n}/reason.txt", text.strip() + "\n", root)


def write_round_spec(name, n, spec, root=None) -> Path:
    """rounds/<n>/spec.json: the settings this round runs with."""
    return _put(name, f"rounds/{_round(n)}/spec.json", _object(spec, "spec"), root)


def write_build(name, n, result, root=None) -> Path:
    """rounds/<n>/build.json: the build's result (lines 2.1-2.9). Refused while the round has no reason on file."""
    _round(n)
    if not (_dir(name, root) / "rounds" / str(n) / "reason.txt").is_file():
        raise ValueError(f"round {n} has no reason on file: the reason is written before the run (line 2.9)")
    return _put(name, f"rounds/{n}/build.json", _object(result, "build"), root)


def write_lock(name, lock, root=None) -> Path:
    """lock.json: the freeze (phase 3) -- the spec, the variants, the default, the control, the costs, `hash`."""
    return _put(name, "lock.json", _object(lock, "lock"), root)


def write_test(name, result, root=None) -> Path:
    """test.json: the out-of-sample test's result (lines 4.1-4.9). An early look's is not the idea's test (the
    toolkit keeps it in early_look/): a result that says "early_look": true never counts, here either."""
    return _put(name, "test.json", _object(result, "test"), root)


def write_sim(name, account, result, root=None) -> Path:
    """sim/<account>.json: the prop simulator's result for one account (lines 5.1-5.4)."""
    if not isinstance(account, str) or not _ID_RE.fullmatch(account):
        raise ValueError("account: a rule set id such as lucid-pro-50k@2026-09-27b")
    return _put(name, f"sim/{account}.json", _object(result, "sim"), root)


def write_eval(name, result, root=None) -> Path:
    """eval.json: the eval card's result (lines 6.1-6.9)."""
    return _put(name, "eval.json", _object(result, "eval"), root)


def add_run(name, run_id, root=None) -> dict:
    """Keep a tester run id with the idea (idea.json `runs`): a run its trades can be looked at in."""
    if not isinstance(run_id, str) or not _ID_RE.fullmatch(run_id):
        raise ValueError("run_id: a tester run id")

    def change(new):
        if run_id not in new["runs"]:
            new["runs"] = [*new["runs"], run_id]
    return _refresh(_dir(name, root), change)


def _log(d: Path, event: str, **fields) -> dict:
    rec = {"utc": _now(), "event": event, **fields}
    with open(d / "log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=_plain) + "\n")
    return rec


def append_log(name, event: str, root=None, **fields) -> dict:
    """One line on the idea's log.jsonl: {utc, event, ...fields}."""
    return _log(_dir(name, root), event, **fields)


def read_idea(name, root=None) -> dict:
    """idea.json as it is on disk."""
    got = _json(_dir(name, root) / "idea.json")
    if got is None:
        raise FileNotFoundError(f"no idea {name!r}")
    return got


def list_ideas(root=None) -> list:
    """Every idea's idea.json, by name. A folder that is not an idea (or whose idea.json does not read) is
    left out."""
    try:
        entries = sorted(p for p in ideas_root(root).iterdir() if p.is_dir())
    except OSError:
        return []
    out = []
    for p in entries:
        try:
            validate_name(p.name)
        except ValueError:
            continue
        got = _json(p / "idea.json")
        if got is not None:
            out.append(got)
    return out


# ---------------------------------------------------------------- the status, from the saved results only

def rounds(name, root=None) -> list:
    """The build rounds on file, in order: [1, 2, ...]."""
    return _rounds(_dir(name, root))


def _rounds(d: Path) -> list:
    return [n for n in range(1, MAX_ROUNDS + 1) if (d / "rounds" / str(n)).is_dir()]


def _finished(r) -> bool:
    """A saved result that counts: not refused, not a dry run, not still running, and it has its lines."""
    if not isinstance(r, dict) or r.get("ok") is False or r.get("dry_run") or not isinstance(r.get("lines"), list):
        return False
    job = r.get("job")
    return not isinstance(job, dict) or job.get("state") == "done"


def _early(r) -> bool:
    """Is this saved result an EARLY LOOK at the test days? It says so itself: "early_look": true."""
    return isinstance(r, dict) and bool(r.get(EARLY_LOOK))


def _early_on_file(d: Path) -> bool:
    """Is an early look's result on file: where the toolkit keeps one (early_look/test.json), or as the
    idea's test.json?"""
    return _early(_json(d / EARLY_LOOK / "test.json")) or _early(_json(d / "test.json"))


def _passed(r: dict, phase: int, waived=()) -> bool:
    """Every line the law has for this phase is in the result and none failed (null = it does not apply). `waived` = lines the lock names
    (lock.json `waived`: the pipeline's variant mode does not ask the build's whole-map lines): a False among them is read as 'not asked'."""
    marks: dict = {}
    for ln in r["lines"]:
        if isinstance(ln, dict) and str(ln.get("line", "")).startswith(f"{phase}."):
            ok = None if ln.get("passed") is False and str(ln["line"]) in waived else ln.get("passed")
            marks.setdefault(str(ln["line"]), []).append(ok)
    said = [m for ms in marks.values() for m in ms]
    if any(m is not True and m is not None for m in said) or not all(k in marks for k in LINES[phase]):
        return False
    if phase == 6 and not all(m is True for k in LIVE_LINES for m in marks[k]):
        return False
    return any(m is True for m in said)


def _build(d: Path) -> tuple:
    """(round, result) of the latest finished build, or (None, None)."""
    for n in reversed(_rounds(d)):
        r = _json(d / "rounds" / str(n) / "build.json")
        if _finished(r):
            return n, r
    return None, None


def _status(d: Path) -> str:
    n, build = _build(d)
    waived = {str(x) for x in ((_json(d / "lock.json") or {}).get("waived") or []) if isinstance(x, str)}
    if build is None or not _passed(build, 2, waived):
        return "shelved" if build is not None and n >= MAX_ROUNDS else "idea"
    test = _json(d / "test.json")
    if not _finished(test) or _early(test):         # an early look proves nothing and shelves nothing
        return "lead"
    if not _passed(test, 4):
        return "shelved"
    ev = _json(d / "eval.json")
    return "proven_live" if _finished(ev) and _passed(ev, 6) else "proven_on_history"


def status(name, root=None) -> str:
    """The idea's status, read off its saved results (the rule is in the module docstring). Never from
    idea.json, and there is no way to set it."""
    return _status(_dir(name, root))


def _phase(d: Path) -> int:
    """The furthest phase with something saved (0 = the card). An early look is not a phase."""
    if (d / "eval.json").is_file():
        return 6
    if any((d / "sim").glob("*.json")):
        return 5
    if (d / "test.json").is_file() and not _early(_json(d / "test.json")):
        return 4
    if (d / "lock.json").is_file():
        return 3
    if _rounds(d):
        return 2
    return 1 if (d / "check.json").is_file() else 0


def _verdict(d: Path) -> dict:
    """The latest saved result that has lines: the furthest phase first. An early look is not a verdict."""
    try:
        sims = sorted((d / "sim").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        sims = []
    builds = [d / "rounds" / str(n) / "build.json" for n in reversed(_rounds(d))]
    for p in [d / "eval.json", *sims, d / "test.json", *builds, d / "check.json"]:
        r = _json(p)
        if r is not None and isinstance(r.get("lines"), list) and not _early(r):
            return r
    return {}


def _summary(d: Path) -> dict:
    """idea.json as the saved files have it: what is read off them (status, phase, round, lines, next,
    early_look = an early look is on file), over what is kept (created, runs, group -- and any field another
    writer keeps there, which is left alone)."""
    old = _json(d / "idea.json") or {}
    v, rs = _verdict(d), _rounds(d)
    lines = [{"line": ln.get("line"), "passed": ln.get("passed"), "text": ln.get("text")}
             for ln in v.get("lines", []) if isinstance(ln, dict)]
    return {**old, "name": d.name, "created": old.get("created") or _now(), "status": _status(d),
            "phase": _phase(d), "round": rs[-1] if rs else None, "lines": lines, "next": v.get("next") or None,
            "early_look": _early_on_file(d),
            "runs": old["runs"] if isinstance(old.get("runs"), list) else [], "group": old.get("group")}


def _refresh(d: Path, change=None) -> dict:
    with _locked(d):
        old, new = _json(d / "idea.json"), _summary(d)
        if change is not None:
            change(new)
        if new != old:
            _write(d / "idea.json", _dumps(new))
    if old is not None and old.get("status") != new["status"]:
        _log(d, "status", was=old.get("status"), now=new["status"])
    return new


def refresh(name, root=None) -> dict:
    """Bring idea.json up to date with the saved results (status, phase, round, lines, next, early_look) and
    return it. Every write_* does it; a change of status goes on the idea's log."""
    return _refresh(_dir(name, root))


# ---------------------------------------------------------------- the one-read log (the test days)

def _parse_reads(text: str) -> list:
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            rec = None
        if not isinstance(rec, dict):
            raise ReadLogUnreadable(f"{READS_FILE} line {i} does not read: fix the file before any read of the "
                                    "test days")
        out.append(rec)
    return out


def reads(root=None) -> list:
    """Every line of the one-read log, oldest first. ReadLogUnreadable when a line does not read."""
    try:
        return _parse_reads((ideas_root(root) / READS_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def read_on_file(name, version=None, lock=None, root=None):
    """Is a read of the test days on file for this idea -- for any version and lock, or for the ones given?
    The latest matching line ({utc, name, version, lock, range, state, verdict}), or None."""
    hits = [r for r in reads(root) if r.get("name") == name and (version is None or r.get("version") == version)
            and (lock is None or r.get("lock") == lock)]
    return hits[-1] if hits else None


@contextmanager
def _reads_locked(root):
    """The read log, open to append and locked: one writer at a time, across processes."""
    p = ideas_root(root) / READS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        yield f, f.read()


def _append_read(f, text: str, rec: dict) -> dict:
    """One line, never rewriting an earlier one, on disk before the call returns."""
    f.write(("" if not text or text.endswith("\n") else "\n") + json.dumps(rec, default=_plain) + "\n")
    f.flush()
    os.fsync(f.fileno())
    return rec


def _read_line(name, version, lock, rng, state, verdict=None, **more) -> dict:
    return {"utc": _now(), "name": validate_name(name), "version": version, "lock": lock, "range": rng,
            "state": state, "verdict": verdict, **more}


def log_read(name, *, version, lock, rng, state, verdict=None, root=None) -> dict:
    """Append one line to the one-read log: `judged` with the verdict once the test is read (or `claimed`,
    without the check -- claim_read() is the claim that refuses a second read)."""
    if state not in READ_STATES:
        raise ValueError("state: claimed or judged")
    rec = _read_line(name, version, lock, rng, state, verdict)
    with _reads_locked(root) as (f, text):
        return _append_read(f, text, rec)


def claim_read(name, *, version, lock, rng, second_look: bool = False, relatives=None, root=None) -> dict:
    """Log THE read of the test days, before they are opened -- once. Checked and written under one lock, so
    of two claims at the same moment one is refused. ReadOnFile when a read is on file for this idea: always
    for the same version and lock; for another version or lock unless `second_look` (the owner's explicit
    second look at a changed rule: the line says so). `relatives` = the related ideas whose reads were on
    file and did not stop this one (a list, kept on the line as it is given; None = the line has no such
    key). It changes nothing of what is refused: an idea's own read is one read."""
    rec = _read_line(name, version, lock, rng, "claimed", **({"second_look": True} if second_look else {}),
                     **({} if relatives is None else {"relatives": list(relatives)}))
    with _reads_locked(root) as (f, text):
        prior = [r for r in _parse_reads(text) if r.get("name") == name]
        same = [r for r in prior if r.get("version") == version and r.get("lock") == lock]
        if same or (prior and not second_look):
            was = (same or prior)[-1]
            raise ReadOnFile(f"a read of the test days is already on file for {name} (version "
                             f"{was.get('version')}, {was.get('utc')}): the test days are read once")
        return _append_read(f, text, rec)


# ---------------------------------------------------------------- the idea's record in the Lab

def lab_dir(root=None, drafts=None) -> Path:
    """The drafts dir an idea's Lab copy goes to: `drafts`, else draftstore's own (HOMEBASE_DRAFTS_DIR, or
    ~/.homebase/strategies for the app's own idea folder). An idea folder that was MOVED (a test, a trial run)
    does not take the Lab with it: it is told where its drafts go, or it is refused -- so it can never write
    the real Lab. ValueError then."""
    if drafts is not None:
        return Path(drafts)
    own = Path.home() / ".homebase" / "ideas"
    if not os.environ.get(draftstore.ENV) and ideas_root(root).resolve() != own.resolve():
        raise ValueError(f"the idea folder is not the app's own ({ideas_root(root)}): say where its Lab drafts go "
                         f"({draftstore.ENV}, or drafts=) -- a moved idea folder never writes the real Lab")
    return draftstore.drafts_dir()


def _market(d: Path) -> str:
    """The futures root of the card's home when it names one (else NQ: a record draft needs some root)."""
    try:
        m = (_json(d / "spec.json") or {})["card"]["home"]["market"]
    except (KeyError, TypeError):
        m = None
    return m if isinstance(m, str) and _ROOT_RE.fullmatch(m) else "NQ"


def draft_block(name, root=None) -> str:
    """The record block as it goes on top of the idea's Lab draft: the status line (which says when an early
    look is on file), the card (card.md) and the latest verdict, every line a comment."""
    d = _dir(name, root)
    s = _summary(d)
    out = [f"{s['name']} · {s['status'].replace('_', ' ').upper()} · phase {s['phase']}"
           + (f" · round {s['round']}" if s["round"] else "") + (" · EARLY LOOK on file" if s["early_look"] else "")]
    try:
        card = (d / "card.md").read_text(encoding="utf-8")
    except OSError:
        card = ""
    if card.strip():
        out += ["", "CARD"] + ["  " + ln for ln in card.splitlines()]
    said = [t for ln in s["lines"] for t in str(ln.get("text") or "").splitlines()]
    if said:
        out += ["", "LATEST VERDICT"] + ["  " + t for t in said]
    if s["next"]:
        out += ["", "NEXT: " + " ".join(str(s["next"]).split())]
    body = "\n".join(("# " + "".join(c if c.isprintable() else " " for c in ln)).rstrip() for ln in out)
    return (f"{BLOCK_START} (the blueprint tools rewrite this block; the code below it is left alone)\n"
            f"{body}\n{BLOCK_END}\n")


def _split_block(text: str) -> tuple:
    """(the record block on top, everything below it). No block on top -- or one whose end line is gone -- is
    ("", the whole text): nothing is cut that this module did not write."""
    if text.startswith(BLOCK_START):
        end = text.find("\n" + BLOCK_END + "\n")
        if end >= 0:
            cut = end + len(BLOCK_END) + 2
            return text[:cut], text[cut:]
    return "", text


def write_draft_block(name, root=None, drafts=None) -> Path:
    """Write or refresh the record block on top of the idea's Lab draft (<drafts dir>/<name>.py), through
    draftstore. The code below the block is left exactly as it is; an idea without a draft gets a record
    draft (RECORD_STUB). Nothing new to say: the file is not rewritten. ValueError when the draft cannot be
    written (it does not read as a draft): the file is then left as it was."""
    d, drafts = _dir(name, root), lab_dir(root, drafts)
    p = draftstore.path_for(name, drafts)
    try:
        old = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        old = None
    below = RECORD_STUB.format(name=name, root=_market(d)) if old is None else _split_block(old)[1]
    new = draft_block(name, root) + below
    if new != old:
        draftstore.write(name, new, base=drafts)
    return p


def group_for(status) -> str:
    """The Lab group an idea of that status is filed under: Ideas, Leads, Proven on history, Proven live,
    Shelved."""
    try:
        return GROUPS[status]
    except (KeyError, TypeError):
        raise ValueError(f"status: one of {', '.join(STATUSES)}") from None


def _file_group(name, group: str, drafts: Path) -> str:
    """File the idea's Lab draft (draft_<name>) under `group`, which is made first when the Lab has none of
    that name. Returns the group as the Lab spells it. ValueError when groups.json does not read."""
    if not any(g.casefold() == group.casefold() for g in draftstore.read_groups(drafts)["groups"]):
        draftstore.add_group(group, drafts)
    sid = draftstore.draft_id(validate_name(name))
    return draftstore.set_group(sid, group, drafts)["members"][sid]


def sync(name, root=None, drafts=None) -> dict:
    """Bring the app's copies up to date with the saved results: idea.json, the record block on the idea's
    Lab draft and -- when the status is not the one last filed -- the Lab group of that draft. Only then:
    while the status stays, the Lab is left alone, so a draft the owner filed elsewhere stays there.
    The Lab is a mirror, never a gate: a draft or a groups.json that cannot be written is said in `notes` and
    tried again on the next sync; nothing is raised for it.
    -> {"idea": idea.json, "filed": the group it was just filed under | None, "notes": [what was not done]}"""
    d = _dir(name, root)
    idea, filed, notes = _refresh(d), None, []
    try:
        drafts = lab_dir(root, drafts)
        write_draft_block(name, root, drafts)
    except (ValueError, OSError) as e:
        return {"idea": idea, "filed": None, "notes": [f"the Lab draft was not updated: {e}"]}
    group = group_for(idea["status"])
    if idea.get("group") != group:
        try:
            filed = _file_group(name, group, drafts)
        except (ValueError, OSError) as e:
            notes.append(f"the Lab group was not updated: {e}")
        else:
            idea = _refresh(d, lambda new: new.update(group=group))
            _log(d, "group", group=filed)
    return {"idea": idea, "filed": filed, "notes": notes}
