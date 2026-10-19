"""The sandbox a DRAFT strategy's backtest runs in: macOS `sandbox-exec` with draft.sb (deny by default), or on
Linux (the VPS, 2026-10-19) bubblewrap with the same rules -- see _bwrap().

    cmd, env, tmp = sandbox.wrap(python_argv, run_dir=..., archive=..., cache=...)

A draft run's child (`runner exec`) is launched only through wrap(): the profile lets it read the Python
install, the venv, the repo's code, the tick archive and the shared tape cache; write only its run dir and a
private tmp dir (its own tape cache goes there: runner --private-cache); no network, no fork, no exec but
the interpreter; and never read homebase/.state, ~/.homebase, ~/.ssh, ~/.zshrc or the keychains. The env is
minimal (no secrets travel through it). FAIL CLOSED: when sandbox-exec is missing or its self-test does not
refuse what it must, available() is False and every draft backtest is refused (SandboxUnavailable).
Built-in strategies never come here.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from ..paths import repo_root

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
PROFILE = Path(__file__).resolve().parent / "draft.sb"
BWRAP = "/usr/bin/bwrap"
LINUX = sys.platform.startswith("linux")
DRAFT_TIMEOUT_S = 20 * 60          # a draft backtest's hard wall clock (runner/grid kill its process group)


class SandboxUnavailable(ValueError):
    """No working sandbox: a draft backtest is refused (fail closed). Shown to the user."""


def _real(p) -> str:
    return os.path.realpath(os.fspath(p))


def params(*, run_dir, archive, cache, tmp, python: str | None = None) -> dict:
    py = python or sys.executable
    home = _real(Path.home())
    return {"PYEXE": os.path.abspath(py), "PYREAL": _real(py), "PYHOME": _real(sys.base_prefix),
            "VENV": _real(sys.prefix), "REPO": _real(repo_root()), "ARCHIVE": _real(archive),
            "CACHE": _real(cache), "RUNDIR": _real(run_dir), "TMP": _real(tmp), "HOME": home,
            "LOCK": os.path.join(_real(Path(run_dir).parent), ".lock")}   # runner's one-run flock file


def _interpreter(p: str, bound: tuple[str, ...]) -> list[str]:
    """bwrap args that make the interpreter's symlink chain exist inside (venv/bin/python -> /usr/bin/python3 ->
    python3.14): each link outside the already-bound trees as a symlink, the real binary as a read-only file."""
    out: list[str] = []
    for _ in range(16):
        inside = any(p == b or p.startswith(b + os.sep) for b in bound)
        if not os.path.islink(p):
            return out if inside else out + ["--ro-bind", p, p]
        t = os.readlink(p)
        if not inside:
            out += ["--symlink", t, p]
        p = os.path.normpath(os.path.join(os.path.dirname(p), t))
    raise SandboxUnavailable(f"the interpreter's symlinks do not end: {p}")


def _bwrap(prm: dict) -> list[str]:
    """The Linux sandbox: draft.sb's rules in bubblewrap terms. Its own empty network and pid space (no socket
    reaches the desk, the chart service or anything else); a read-only root made of the system libraries, /etc,
    the interpreter binary, the repo (with homebase/.state hidden under an empty tmpfs), the venv, the tick
    archive and the tape cache -- HOME is not there at all, so ~/.homebase, ~/.ssh and the shell rc do not
    exist inside; read + write only its run dir, its tmp dir and the runs' lock file. Programs are not mounted
    (no /usr/bin, /bin), so exec of anything but the interpreter finds nothing.
    shortcut: fork is not refused here (macOS refuses it); the child dies with its parent and the runner kills
    its process group on timeout. Add a seccomp filter if a draft is ever not our own code."""
    repo, lock = prm["REPO"], prm["LOCK"]
    try:
        open(lock, "a").close()                     # a bind needs the file; the runner flocks it (append)
    except OSError:
        pass
    a = [BWRAP, "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
         "--ro-bind", "/usr/lib", "/usr/lib", "--ro-bind-try", "/usr/lib64", "/usr/lib64",
         "--ro-bind", "/usr/share", "/usr/share", "--ro-bind-try", "/usr/local/lib", "/usr/local/lib",
         "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
         "--ro-bind", "/etc", "/etc", "--proc", "/proc", "--dev", "/dev",
         "--ro-bind", repo, repo, "--tmpfs", os.path.join(repo, "homebase", ".state"),
         "--ro-bind", prm["VENV"], prm["VENV"],
         "--ro-bind-try", prm["ARCHIVE"], prm["ARCHIVE"], "--ro-bind-try", prm["CACHE"], prm["CACHE"]]
    a += _interpreter(prm["PYEXE"], (repo, prm["VENV"], "/usr/lib", "/usr/share"))
    a += ["--bind", prm["RUNDIR"], prm["RUNDIR"], "--bind", prm["TMP"], prm["TMP"], "--bind-try", lock, lock,
          "--chdir", prm["TMP"]]
    return a


def command(argv: list[str], prm: dict) -> list[str]:
    if LINUX:
        return _bwrap(prm) + list(argv)
    cmd = [SANDBOX_EXEC, "-f", str(PROFILE)]
    for k, v in prm.items():
        cmd += ["-D", f"{k}={v}"]
    return cmd + list(argv)


def env(tmp) -> dict:
    """The child's whole environment: nothing inherited but what a backtest needs."""
    keep = {k: os.environ[k] for k in ("HOMEBASE_TESTER_SHARED", "TZ", "LANG") if k in os.environ}
    return {**keep, "PATH": "/usr/bin:/bin", "HOME": _real(Path.home()), "TMPDIR": _real(tmp),
            "PYTHONPATH": _real(repo_root()), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "HOMEBASE_SANDBOXED": "1"}


def private_tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="hb-draft-"))


def drop_tmp(tmp) -> None:
    shutil.rmtree(tmp, ignore_errors=True)


_ok: list = []
_lock = threading.Lock()

# argv: a dir outside its own, a port this process is LISTENING on, the repo's homebase/.state. Every try must
# fail: macOS answers PermissionError; bubblewrap answers from inside (its own empty network refuses, a hidden
# path is missing) -- either way nothing reached the listener, nothing was created and .state shows nothing.
_PROBE = ("import os, socket, sys\n"
          "try:\n"
          "    socket.create_connection(('127.0.0.1', int(sys.argv[2])), timeout=1)\n"
          "    sys.exit(3)\n"
          "except OSError:\n"
          "    pass\n"
          "try:\n"
          "    open(os.path.join(sys.argv[1], 'probe'), 'x').close()\n"
          "    sys.exit(4)\n"
          "except OSError:\n"
          "    pass\n"
          "try:\n"
          "    if os.listdir(sys.argv[3]):\n"
          "        sys.exit(5)\n"
          "except OSError:\n"
          "    pass\n"
          "print('sandboxed')\n")


def _tool_ok() -> bool:
    if LINUX:
        return os.access(BWRAP, os.X_OK)
    return os.access(SANDBOX_EXEC, os.X_OK) and PROFILE.is_file()


def available() -> bool:
    """True once a probe child, run in the sandbox, printed 'sandboxed': it could not reach a port this process
    listens on, could not create a file outside its dirs and could not list homebase/.state -- and the listener
    saw no connection. Cached per process (a failure is re-probed next time)."""
    with _lock:
        if _ok:
            return True
        if not _tool_ok():
            return False
        tmp = private_tmp()
        outside = private_tmp()
        srv = socket.socket()
        try:
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            srv.settimeout(0.2)
            state = os.path.join(_real(repo_root()), "homebase", ".state")
            prm = params(run_dir=tmp, archive=tmp, cache=tmp, tmp=tmp)
            argv = [sys.executable, "-c", _PROBE, str(outside), str(srv.getsockname()[1]), state]
            p = subprocess.run(command(argv, prm), env=env(tmp), capture_output=True, text=True, timeout=30, cwd=tmp)
            good = p.returncode == 0 and p.stdout.strip() == "sandboxed" and not (outside / "probe").exists()
            try:
                srv.accept()[0].close()
                good = False                        # something reached the listener: no sandbox
            except OSError:
                pass
        except (OSError, subprocess.SubprocessError, SandboxUnavailable):
            good = False
        finally:
            srv.close()
            drop_tmp(tmp)
            drop_tmp(outside)
        if good:
            _ok.append(True)
        return good


def require() -> None:
    if not available():
        tool = ("the Linux sandbox (bubblewrap, /usr/bin/bwrap)" if LINUX
                else "the macOS sandbox (sandbox-exec + homebase/backtest/draft.sb)")
        raise SandboxUnavailable(f"draft strategies run only inside {tool}, and it is not working here: draft "
                                 "backtests are refused")
