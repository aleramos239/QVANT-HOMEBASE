"""The sandbox a DRAFT strategy's backtest runs in: macOS `sandbox-exec` with draft.sb (deny by default).

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
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from ..paths import repo_root

SANDBOX_EXEC = "/usr/bin/sandbox-exec"
PROFILE = Path(__file__).resolve().parent / "draft.sb"
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


def command(argv: list[str], prm: dict) -> list[str]:
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

_PROBE = ("import os, socket, sys\n"
          "try:\n"
          "    socket.create_connection(('127.0.0.1', 9), timeout=1)\n"
          "    sys.exit(3)\n"
          "except PermissionError:\n"
          "    pass\n"
          "except OSError:\n"
          "    sys.exit(3)\n"
          "try:\n"
          "    open(os.path.join(sys.argv[1], 'probe'), 'x').close()\n"
          "    sys.exit(4)\n"
          "except PermissionError:\n"
          "    pass\n"
          "print('sandboxed')\n")


def available() -> bool:
    """True once a probe child, run under the profile, printed 'sandboxed': it could not open a socket and
    could not create a file outside its dirs. Cached per process (a failure is re-probed next time)."""
    with _lock:
        if _ok:
            return True
        if not os.access(SANDBOX_EXEC, os.X_OK) or not PROFILE.is_file():
            return False
        tmp = private_tmp()
        outside = private_tmp()
        try:
            prm = params(run_dir=tmp, archive=tmp, cache=tmp, tmp=tmp)
            p = subprocess.run(command([sys.executable, "-c", _PROBE, str(outside)], prm), env=env(tmp),
                               capture_output=True, text=True, timeout=30, cwd=tmp)
            good = p.returncode == 0 and p.stdout.strip() == "sandboxed" and not (outside / "probe").exists()
        except (OSError, subprocess.SubprocessError):
            good = False
        finally:
            drop_tmp(tmp)
            drop_tmp(outside)
        if good:
            _ok.append(True)
        return good


def require() -> None:
    if not available():
        raise SandboxUnavailable("draft strategies run only inside the macOS sandbox (sandbox-exec + "
                                 "homebase/backtest/draft.sb), and it is not working here: draft backtests are "
                                 "refused")
